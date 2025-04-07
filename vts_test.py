import pyvts
import asyncio

plugin_info = {
    "plugin_name": "MaiBot-Vtuber",
    "developer": "ChangingSelf",
    "authentication_token_path": "./token.txt",
}


async def main():
    # 连接VTS
    vts = pyvts.vts(plugin_info=plugin_info)
    await vts.connect()
    await vts.request_authenticate_token()
    await vts.request_authenticate()

    # 获取所有动画
    response_data = await vts.request(vts.vts_request.requestHotKeyList())

    # 获取所有动画名称
    hotkey_list = []
    for hotkey in response_data["data"]["availableHotkeys"]:
        hotkey_list.append(hotkey["name"])
    print(hotkey_list)
    send_hotkey_request = vts.vts_request.requestTriggerHotKey(
        hotkey_list[1]
    )  # 调用第一个动画
    await vts.request(send_hotkey_request)
    await vts.close()


if __name__ == "__main__":
    asyncio.run(main())
