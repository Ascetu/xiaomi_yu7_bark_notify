import argparse
import json
import logging
import sys
import requests
import time
from datetime import datetime

API_URL = "https://api.retail.xiaomiev.com/mtop/guidemarketing/product/car/inventory/list"

HEADERS_TEMPLATE = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/132.0.0.0 Safari/537.36 "
                  "MicroMessenger/7.0.20.1781(0x6700143B) NetType/WIFI "
                  "MiniProgramEnv/Mac MacWechat/WMPF MacWechat/3.8.7(0x13080712) "
                  "UnifiedPCMacWechat(0xf2641411) XWEB/16990",
    "Content-Type": "application/json; charset=UTF-8",
    "deviceappversion": "1.19.2",
    "configSelectorVersion": "2",
    "x-user-agent": "channel/car platform/car.wxlite",
    "xweb_xhr": "1",
    "Referer": "https://servicewechat.com/wx183d85f5e5e273c6/124/page-frame.html",
    "Accept-Language": "zh-CN,zh;q=0.9",
}


# PAYLOAD = [{
#     "source": "wx",
#     "inventoryChannel": "NORMAL",
#     "conditions": {
#         "stockType": "all",
#         "itemType": "500015457",
#         "sortType": "priceAsc"
#     },
#     "pageNo": 1,
#     "pageSize": 200
# }]
PAYLOAD = [{
    "source": "wx",
    "inventoryChannel": "NORMAL",
    "conditions": {
        "stockType": "all",
        "itemType": "500015457",
        "sortType": "priceAsc",
        # "carSsuId": "600019694",
        "carSsuId": "600019693",
        "saleConfigFilterList": []
    },
    "pageNo": 1,
    "pageSize": 200
}]


def setup_logger():
    logging.basicConfig(
        level=logging.WARNING,
        format="%(message)s"
    )
    return logging.getLogger(__name__)


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--cookie", required=True, help="serviceTokenCar Cookie")
    return parser.parse_args()


def request_inventory(cookie: str) -> dict:
    headers = HEADERS_TEMPLATE.copy()
    headers["Cookie"] = cookie

    resp = requests.post(
        API_URL,
        headers=headers,
        data=json.dumps(PAYLOAD),
        timeout=15
    )

    if resp.status_code != 200:
        raise RuntimeError(f"HTTP 请求失败，状态码：{resp.status_code}")

    return resp.json()


def match_ssu_info(ssu_info: str) -> bool:
    if not ssu_info:
        return False

    color_ok = "深海蓝" in ssu_info
    wheel_ok = ("幻刃轮毂" in ssu_info) or ("锻造梅花轮毂" in ssu_info)
    audio_ok = "豪华音响" in ssu_info
    # interior_ok = ("松石灰" in ssu_info) or ("鸢尾紫" in ssu_info) or ("珊瑚橙" in ssu_info)
    interior_ok = ("松石灰" in ssu_info) or ("鸢尾紫" in ssu_info)

    return color_ok and wheel_ok and audio_ok and interior_ok


def query_inventory(cookie, logger):
    """执行一次接口请求并输出匹配结果"""
    try:
        resp_json = request_inventory(cookie)
    except Exception as e:
        logger.error(f"接口请求失败：{e}")
        return False

    # 接口返回校验日志
    code = resp_json.get("code")
    message = resp_json.get("message")
    data = resp_json.get("data", {})
    total = data.get("total")

    logger.warning("========== 接口返回校验 ==========")
    logger.warning(f"code: {code}")
    logger.warning(f"message: {message}")
    logger.warning(f"total: {total}")
    logger.warning("=================================")

    if code != 0 or not data:
        logger.error("接口返回非成功状态或 data 为空")
        return False

    items = data.get("items", [])
    if not items:
        logger.warning("接口返回 items 为空")
        return False

    matched = []

    for item in items:
        ssu_info = item.get("ssuInfo", "")
        if match_ssu_info(ssu_info):
            matched.append({
                "classify": item.get("classify"),
                "marketPrice": item.get("marketPrice"),
                "ssuInfo": ssu_info
            })

    if not matched:
        logger.warning("未发现满足条件的现车配置")
        return False

    logger.warning("========== 命中现车配置 ==========")
    for idx, car in enumerate(matched, 1):
        logger.warning(f"[{idx}] classify: {car['classify']}")
        logger.warning(f"    marketPrice: {car['marketPrice']}")
        logger.warning(f"    ssuInfo: {car['ssuInfo']}")
    logger.warning("==================================")
    return True


def main():
    logger = setup_logger()
    args = parse_args()

    # 循环 sleep 时间序列（秒）
    sleep_times = [0, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55, 65]

    logger.warning("========== 库存接口查询循环开始 ==========")

    start_time = datetime.now()

    for idx, s in enumerate(sleep_times):
        if idx > 0:
            time.sleep(s - sleep_times[idx - 1])

        now = datetime.now()
        hour = now.hour
        minute = now.minute

        # 严格判断当前时间窗口，只执行刷新窗口前
        if (hour == 11 or hour == 23) or (hour == 10 or hour == 22):
            hit = query_inventory(args.cookie, logger)
            if hit:
                logger.warning(f"命中刷新窗口，退出循环，当前时间：{now}")
                break
        else:
            # 当前时间不在目标窗口，跳过循环
            logger.warning(f"跳过循环，当前时间：{now}")
            continue

    logger.warning("========== 库存接口查询循环结束 ==========")


if __name__ == "__main__":
    main()
