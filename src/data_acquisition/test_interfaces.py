import time
import akshare as ak
import requests
import pandas as pd
from src.logger import logger

def test_eastmoney_all():
    """测试东方财富全市场接口 (Akshare)"""
    logger.info("1. 正在测试东方财富全市场接口 (ak.stock_zh_a_spot_em)...")
    try:
        start = time.time()
        df = ak.stock_zh_a_spot_em()
        elapsed = time.time() - start
        logger.info(f"✅ 东方财富接口成功! 获取 {len(df)} 条数据, 耗时 {elapsed:.2f}s")
        print(df.head(3))
        return True
    except Exception as e:
        logger.error(f"❌ 东方财富接口失败: {e}")
        return False

def test_sina_snapshot(codes=['sh600519', 'sz000001']):
    """测试新浪财经接口 (直接请求)"""
    logger.info("2. 正在测试新浪财经接口 (http://hq.sinajs.cn)...")
    try:
        # 新浪接口需要加上交易所前缀: sh/sz
        url = f"http://hq.sinajs.cn/list={','.join(codes)}"
        headers = {'Referer': 'http://finance.sina.com.cn/'}
        start = time.time()
        resp = requests.get(url, headers=headers, timeout=5)
        elapsed = time.time() - start
        
        if resp.status_code == 200 and "var hq_str_" in resp.text:
            logger.info(f"✅ 新浪接口成功! 耗时 {elapsed:.2f}s")
            print(f"响应预览: {resp.text[:100]}...")
            return True
        else:
            logger.error(f"❌ 新浪接口响应异常: {resp.status_code}")
            return False
    except Exception as e:
        logger.error(f"❌ 新浪接口失败: {e}")
        return False

def test_tencent_snapshot(codes=['sh600519', 'sz000001']):
    """测试腾讯财经接口 (直接请求)"""
    logger.info("3. 正在测试腾讯财经接口 (http://qt.gtimg.cn)...")
    try:
        url = f"http://qt.gtimg.cn/q={','.join(codes)}"
        start = time.time()
        resp = requests.get(url, timeout=5)
        elapsed = time.time() - start
        
        if resp.status_code == 200 and "v_" in resp.text:
            logger.info(f"✅ 腾讯接口成功! 耗时 {elapsed:.2f}s")
            print(f"响应预览: {resp.text[:100]}...")
            return True
        else:
            logger.error(f"❌ 腾讯接口响应异常: {resp.status_code}")
            return False
    except Exception as e:
        logger.error(f"❌ 腾讯接口失败: {e}")
        return False

if __name__ == '__main__':
    logger.info("=== 开始接口连通性测试 ===")
    em_success = test_eastmoney_all()
    sina_success = test_sina_snapshot()
    tx_success = test_tencent_snapshot()
    
    logger.info("=== 测试总结 ===")
    logger.info(f"东方财富: {'可用' if em_success else '不可用'}")
    logger.info(f"新浪财经: {'可用' if sina_success else '不可用'}")
    logger.info(f"腾讯财经: {'可用' if tx_success else '不可用'}")

