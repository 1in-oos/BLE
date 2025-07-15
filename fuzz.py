import asyncio
import random
import logging
from datetime import datetime
from bleak import BleakScanner, BleakClient, BleakError

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler(f"ble_fuzz_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"),
        logging.StreamHandler()
    ]
)

class BleFuzzer:
    def __init__(self, device_address, write_times=5, read_times=3, notify_time=10, reconnect_attempts=3, write_delay=1.0):
        self.device_address = device_address
        self.client = None
        self.write_times = write_times
        self.read_times = read_times
        self.notify_time = notify_time
        self.reconnect_attempts = reconnect_attempts  # 断线后重连最大次数
        self.write_delay = write_delay  # 写入间隔，秒
        self.notifications = {}

    async def connect(self):
        for attempt in range(1, self.reconnect_attempts + 1):
            try:
                self.client = BleakClient(self.device_address)
                await self.client.connect()
                logging.info(f"已连接设备 {self.device_address} (尝试 {attempt}/{self.reconnect_attempts})")
                await self.client.get_services()
                return True
            except BleakError as e:
                logging.error(f"连接失败 (尝试 {attempt}): {e}")
                if attempt < self.reconnect_attempts:
                    await asyncio.sleep(2)  # 等待2秒后重试
        return False

    async def disconnect(self):
        if self.client and self.client.is_connected:
            await self.client.disconnect()
            logging.info(f"已断开设备 {self.device_address}")

    def generate_payloads(self):
        # 异常数据集合：超长、边界值、特殊格式
        payloads = [
            b'',  # 空数据
            bytes([0x00]),  # 单字节零
            bytes([0xFF]),  # 单字节全1
            bytes(range(20)),  # 0-19递增
            bytes([0xFF]*20),  # 20字节全0xFF
            bytes([0x00]*512),  # 512字节全0
            bytes([random.getrandbits(8) for _ in range(512)]),  # 512字节随机
            b'\x00\xFF'*10,  # 特殊交替格式
            b'\xAA'*1000,  # 超长1000字节
        ]
        return payloads

    async def fuzz_write_characteristic(self, char):
        logging.info(f"开始对特征 {char.uuid} 进行写入异常数据测试，共{self.write_times}次")
        payloads = self.generate_payloads()
        count = 0
        for i in range(self.write_times):
            payload = random.choice(payloads)
            try:
                if not self.client.is_connected:
                    logging.warning("连接断开，尝试重新连接...")
                    if not await self.connect():
                        logging.error("重连失败，终止写入测试")
                        return

                await self.client.write_gatt_char(char.uuid, payload)
                logging.info(f"  写入成功 ({len(payload)}字节): {payload.hex()[:60]}{'...' if len(payload)>30 else ''}")
            except Exception as e:
                logging.error(f"  写入失败: {e}")
            count += 1
            await asyncio.sleep(self.write_delay)  # 控制写入节奏，避免设备过载

    async def fuzz_read_characteristic(self, char):
        logging.info(f"开始对特征 {char.uuid} 进行读取异常测试，共{self.read_times}次")
        for i in range(self.read_times):
            try:
                if not self.client.is_connected:
                    logging.warning("连接断开，尝试重新连接...")
                    if not await self.connect():
                        logging.error("重连失败，终止读取测试")
                        return

                data = await self.client.read_gatt_char(char.uuid)
                logging.info(f"  读取成功: {data.hex()[:60]}{'...' if len(data)>30 else ''}")
            except Exception as e:
                logging.error(f"  读取失败: {e}")
            await asyncio.sleep(self.write_delay)

    def notification_handler(self, sender, data):
        logging.info(f"收到通知 from {sender}: {data.hex()[:60]}{'...' if len(data)>30 else ''}")
        self.notifications[sender] = data

    async def subscribe_notifications(self, char):
        logging.info(f"开始订阅通知: {char.uuid}")
        try:
            await self.client.start_notify(char.uuid, self.notification_handler)
            await asyncio.sleep(self.notify_time)
            await self.client.stop_notify(char.uuid)
            logging.info(f"停止订阅通知: {char.uuid}")
        except Exception as e:
            logging.error(f"通知订阅失败: {e}")

    async def run_fuzz_tests(self):
        if not await self.connect():
            return

        try:
            services = self.client.services
            logging.info(f"发现 {len(services)} 个服务")

            for service in services:
                logging.info(f"[Service] {service.uuid} - {service.description}")
                for char in service.characteristics:
                    props = char.properties
                    logging.info(f"  [Characteristic] {char.uuid} ({','.join(props)})")

                    if "write" in props or "write-without-response" in props:
                        await self.fuzz_write_characteristic(char)

                    if "read" in props:
                        await self.fuzz_read_characteristic(char)

                    if "notify" in props:
                        await self.subscribe_notifications(char)

        finally:
            await self.disconnect()

async def scan_and_test_all(write_times=5, read_times=3, notify_time=10):
    logging.info("开始扫描设备...")
    devices = await BleakScanner.discover(timeout=5.0)

    if not devices:
        logging.info("未发现设备，退出")
        return

    for i, d in enumerate(devices):
        logging.info(f"{i}: {d.name} [{d.address}] RSSI: {d.rssi}")

    target = devices[0]
    logging.info(f"\n选择设备: {target.name} [{target.address}]")

    fuzzer = BleFuzzer(target.address, write_times, read_times, notify_time)
    await fuzzer.run_fuzz_tests()


if __name__ == "__main__":
    asyncio.run(scan_and_test_all(write_times=10, read_times=5, notify_time=10))
