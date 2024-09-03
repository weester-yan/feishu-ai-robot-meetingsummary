import logging


class FeishuClient():
    def __init__(self, bot, *args, **kwargs):
        self.bot = bot

    def get_meeting_list_by_no(self, meeting_no, start_time, end_time, headers=None):
        # 根据会议号获取会议ID
        url = f"{self.bot.host}/open-apis/vc/v1/meetings/list_by_no?meeting_no={meeting_no}&start_time={start_time}&end_time={end_time}"
        logging.info("Request: %r", url)
        response =  self.bot.get(url) if not headers else self.bot.get(url, headers=headers)
        logging.info("Response: %r", (response.status_code, response.content))
        return response

    def get_record(self, meeting_id, headers=None):
        # 根据会议ID获取会议录制文件地址
        url = f"{self.bot.host}/open-apis/vc/v1/meetings/{meeting_id}/recording"
        logging.info("request url: %r", url)
        response = self.bot.get(url) if not headers else self.bot.get(url, headers=headers)
        logging.info("Response: %r", (response.status_code, response.content))
        return response

    def get_meeting(self, meeting_id, headers=None):
        # 获取会议详情
        url = f"{self.bot.host}/open-apis/vc/v1/meetings/{meeting_id}?with_participants=true"
        logging.info("request url: %r", url)
        response = self.bot.get(url) if not headers else self.bot.get(url, headers=headers)
        logging.info("Response: %r", (response.status_code, response.content))
        return response

    def get_record_minute(self, minute_token, headers=None):
        # 导出妙计文件内容
        url = f"{self.bot.host}/open-apis/minutes/v1/minutes/{minute_token}/transcript"
        logging.info("request url: %r", url)
        response = self.bot.get(url) if not headers else self.bot.get(url, headers=headers)
        logging.info("Response: %r", (response.status_code, len(response.content)))
        return response

    def get_minute(self, minute_token, headers=None):
        # 获取妙计详情
        url = f"{self.bot.host}/open-apis/minutes/v1/minutes/{minute_token}"
        logging.info("request url: %r", url)
        response = self.bot.get(url) if not headers else self.bot.get(url, headers=headers)
        logging.info("Response: %r", (response.status_code, response.content))
        return response

    def submit_summary_task(self, body, headers=None):
        # 提交会议智能总结任务
        url = f"{self.bot.host}/open-apis/audio_video_ai/v1/meeting_assistance"
        logging.info("request url: %r", url)
        response = self.bot.post(url, json=body) if not headers else self.bot.post(url, json=body, headers=headers)
        logging.info("Response: %r", (response.status_code, response.content))
        return response

    def get_summary_task(self, task_id, headers=None):
        # 查询总结任务详情
        url = f"{self.bot.host}/open-apis/audio_video_ai/v1/meeting_assistance?task_id={task_id}"
        logging.info("request url: %r", url)
        response = self.bot.get(url) if not headers else self.bot.get(url, headers=headers)
        logging.info("Response: %r", (response.status_code, response.content))
        return response

    def create_docx(self, body, headers=None):
        # 创建云文档
        url = f"{self.bot.host}/open-apis/docx/v1/documents"
        logging.info("request url: %r", url)
        response = self.bot.post(url, json=body) if not headers else self.bot.post(url, json=body, headers=headers)
        logging.info("Response: %r", (response.status_code, response.content))
        return response

    def create_block(self, body, document_id=None, block_id=None, headers=None):
        # 创建块
        url = f"{self.bot.host}/open-apis/docx/v1/documents/{document_id}/blocks/{block_id}/children"
        logging.info("request url: %r", url)
        response = self.bot.post(url, json=body) if not headers else self.bot.post(url, json=body, headers=headers)
        logging.info("Response: %r", (response.status_code, response.content))
        return response

    def send_message_batch(self, body, headers=None):
        # 批量发送消息
        url = f"{self.bot.host}/open-apis/message/v4/batch_send/"
        logging.info("request url: %r", url)
        response = self.bot.post(url, json=body) if not headers else self.bot.post(url, json=body, headers=headers)
        logging.info("Response: %r", (response.status_code, response.content))
        return response

    def get_message(self, message_id, headers=None):
        url = f"{self.bot.host}/open-apis/im/v1/messages/{message_id}"
        logging.info("request url: %r", url)
        response = self.bot.get(url) if not headers else self.bot.get(url, headers=headers)
        logging.info("Response: %r", (response.status_code, response.content))
        return response
