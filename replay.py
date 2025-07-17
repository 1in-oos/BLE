import asyncio
from bleak import BleakClient, BleakScanner

# 你的目标设备 MAC 地址
ADDRESS = "ee:36:44:e4:e6:e9"  # 替换成目标地址

# 你的目标 Handle（通常转换为 UUID 或者直接写 Handle，不同库不同，这里写 UUID 比通用）
# 这里示例用 Handle -> UUID 映射，你需要扫描设备特征找到对应 UUID。
CHARACTERISTIC_UUID = "000000160000351221180009af100700"  # 替换成你的特征 UUID

# 要写入的数据
WRITE_VALUE = bytes.fromhex("030f0004000200000090004cdf3620776743da285792f294e41716")


async def main():
    device = await BleakScanner.find_device_by_address(ADDRESS, timeout=10.0)
    if not device:
        print(f"未找到设备 {ADDRESS}")
        return

    async with BleakClient(device) as client:
        if client.is_connected:
            print(f"已连接到 {ADDRESS}")
            await client.write_gatt_char(CHARACTERISTIC_UUID, WRITE_VALUE, response=False)
            print(f"已发送数据: {WRITE_VALUE.hex()}")
        else:
            print("连接失败")


asyncio.run(main())
