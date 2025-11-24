import unittest
from unittest.mock import patch, MagicMock
import pandas as pd
import sys
import os

# 添加项目根目录到 sys.path
sys.path.append(os.getcwd())

from src.data_acquisition import data_fetcher

class TestDataFetcher(unittest.TestCase):

    @patch('src.data_acquisition.data_fetcher.requests.get')
    def test_fetch_stock_money_flow_realtime(self, mock_get):
        # 模拟东财 fflow 接口返回
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'data': {
                'klines': [
                    # 格式: "时间,主力净流入,小单净流入,中单净流入,大单净流入,超大单净流入"
                    "2023-01-01 09:30,1000000,10000,20000,30000,970000" 
                ]
            }
        }
        mock_get.return_value = mock_response

        result = data_fetcher.fetch_stock_money_flow_realtime("sh600519")
        
        self.assertTrue(result.get('is_net_only'))
        self.assertEqual(result['main_net_inflow'], 1000000)
        # 散户 = 小单 + 中单 = 10000 + 20000 = 30000
        self.assertEqual(result['retail_net_inflow'], 30000) 
        self.assertEqual(result['super_large_net'], 970000)

    @patch('src.data_acquisition.data_fetcher.requests.get')
    def test_fetch_stock_minute_data(self, mock_get):
        # 模拟腾讯分时接口返回
        mock_response = MagicMock()
        mock_response.status_code = 200
        # 腾讯接口格式: data -> code -> data -> data -> ["HHMM price cum_vol avg_price"]
        mock_response.json.return_value = {
            'data': {
                'sh600519': {
                    'data': {
                        'data': [
                            "0930 100.0 100 100.0",
                            "0931 101.0 200 100.5"
                        ]
                    }
                }
            }
        }
        mock_get.return_value = mock_response

        df = data_fetcher.fetch_stock_minute_data("sh600519")
        
        self.assertFalse(df.empty)
        self.assertEqual(len(df), 2)
        self.assertIn('volume', df.columns)
        # 检查第二条数据的成交量是否为增量 (200 - 100 = 100)
        self.assertEqual(df.iloc[1]['volume'], 100 * 100) # 100手 * 100

    @patch('src.data_acquisition.data_fetcher.ak')
    def test_fetch_all_stock_list(self, mock_ak):
        # 模拟 Akshare 返回
        mock_ak.stock_info_sh_a_code_name.return_value = pd.DataFrame({'证券代码': ['600000'], '证券简称': ['浦发银行']})
        mock_ak.stock_info_sz_a_code_name.return_value = pd.DataFrame({'证券代码': ['000001'], '证券简称': ['平安银行']})
        
        df = data_fetcher.fetch_all_stock_list()
        
        self.assertFalse(df.empty)
        self.assertEqual(len(df), 2)
        self.assertTrue('code' in df.columns)
        self.assertTrue('name' in df.columns)
        self.assertIn('600000', df['code'].values)

if __name__ == '__main__':
    unittest.main()
