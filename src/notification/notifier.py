import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.header import Header
from abc import ABC, abstractmethod
from typing import List
from datetime import datetime

from src.config import config
from src.logger import logger

class BaseNotifier(ABC):
    """
    通知器基类，定义统一的接口。
    """
    @abstractmethod
    def send(self, title: str, message: str):
        pass

class EmailNotifier(BaseNotifier):
    """
    邮件通知器。
    """
    def __init__(self):
        self.server = config.MAIL_SERVER
        self.port = config.MAIL_PORT
        self.use_ssl = config.MAIL_USE_SSL
        self.username = config.MAIL_USERNAME
        self.password = config.MAIL_PASSWORD
        self.sender = config.MAIL_SENDER
        self.receiver = config.MAIL_RECEIVER

    def send(self, title: str, message: str):
        """
        发送HTML格式的邮件。
        """
        if not self.username or not self.receiver:
            logger.warning("邮件配置不完整 (用户名或接收者为空)，跳过发送。")
            return

        msg = MIMEMultipart()
        msg['From'] = self.sender
        msg['To'] = self.receiver
        msg['Subject'] = Header(title, 'utf-8')

        # 邮件正文内容
        msg.attach(MIMEText(message, 'html', 'utf-8'))

        try:
            if self.use_ssl:
                server = smtplib.SMTP_SSL(self.server, self.port)
            else:
                server = smtplib.SMTP(self.server, self.port)
                # server.starttls() # 如果非SSL端口支持TLS

            # 登录并发送
            server.login(self.username, self.password)
            server.sendmail(self.sender, [self.receiver], msg.as_string())
            server.quit()
            
            logger.info(f"邮件通知已发送至 {self.receiver}")
            
        except Exception as e:
            logger.error(f"邮件发送失败: {e}")

    def send_signals_report(self, signals: List[dict]):
        """
        发送信号汇总报告。
        """
        if not signals:
            return

        today_str = datetime.now().strftime("%Y-%m-%d")
        title = f"【PG量化】策略信号日报 ({today_str})"
        
        # 构建 HTML 表格
        html_content = f"""
        <h3>策略扫描结果 - {today_str}</h3>
        <p>今日共发现 <b>{len(signals)}</b> 个交易信号：</p>
        <table border="1" style="border-collapse: collapse; width: 100%;">
            <tr style="background-color: #f2f2f2;">
                <th>代码</th>
                <th>策略</th>
                <th>类型</th>
                <th>价格</th>
                <th>描述</th>
            </tr>
        """
        
        for s in signals:
            color = "red" if s['signal_type'] == 'BUY' else "green"
            html_content += f"""
            <tr>
                <td>{s['code']}</td>
                <td>{s['strategy_name']}</td>
                <td style="color: {color}; font-weight: bold;">{s['signal_type']}</td>
                <td>{s['price']:.2f}</td>
                <td>{s.get('description', '')}</td>
            </tr>
            """
            
        html_content += "</table><p>请登录系统看板查看详情。</p>"
        
        self.send(title, html_content)

if __name__ == '__main__':
    # 测试代码
    print("--- Email Notifier Test ---")
    if config.MAIL_USERNAME:
        notifier = EmailNotifier()
        notifier.send("测试邮件", "<h1>你好</h1><p>这是一封来自 PG_Anlize_Sys 的测试邮件。</p>")
    else:
        print("未配置邮件账户，跳过测试。请在 .env 中配置 MAIL_USERNAME 等。")


