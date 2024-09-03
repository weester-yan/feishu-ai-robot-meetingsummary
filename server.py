import copy
import os
import time
import json
import datetime
import logging
import asyncio
import threading
import queue
import locale

from dotenv import find_dotenv, load_dotenv
from urllib.parse import urlencode, quote
from feishu import FeishuClient
from config import *

from connectai.lark.oauth import Server as OauthServer
from connectai.lark.sdk import Bot, MarketBot
from connectai.lark.webhook import LarkServer
from connectai.storage import ExpiredDictStorage
from langchain_openai import ChatOpenAI
from langchain.schema import (
    get_buffer_string,
    HumanMessage,
    AIMessage,
    SystemMessage,
    ChatMessage,
    FunctionMessage
)

load_dotenv(find_dotenv())

logging.basicConfig(level=logging.INFO)
hook = LarkServer()
oauth = OauthServer()
bot = Bot(
    app_id=os.environ.get("APP_ID") or APP_ID,
    app_secret=os.environ.get("APP_SECRET") or APP_SECRET,
    encrypt_key=os.environ.get("ENCRYPT_KEY") or ENCRYPT_KEY,
    verification_token=os.environ.get("VERIFICATION_TOKEN") or VERIFICATION_TOKEN,
    # storage=ExpiredDictStorage(items={}),
    host=os.environ.get("HOST") or HOST
)

meeting_queue = queue.Queue()
def meeting_handler():
    while True:
        event_id, event, bot = meeting_queue.get()
        logging.info("============================ event_id: {}".format(event_id))
        logging.info(">>> event_info: %r", event)

        meeting_no = event["meeting"]["meeting_no"]
        meeting_topic = event["meeting"]["topic"]
        meeting_source = event["meeting"]["meeting_source"]
        start_time = str(int(event["meeting"]["start_time"]) - 1)
        end_time = event["meeting"]["end_time"]
        open_id = event["meeting"]["owner"]["id"]["open_id"]
        card_content = {
            "config": {},
            "header": {
                "title": {
                    "tag": "plain_text",
                    "content": meeting_topic + " - 智能纪要"
                },
                "template": "default"
            },
            "elements": [
                {
                    "tag": "note",
                    "elements": [
                        {
                            "tag": "plain_text",
                            "content": get_gmt_time(start_time, end_time)
                        }
                    ]
                },
                {
                    "tag": "markdown",
                    "content": "",
                    "text_align": "left",
                    "text_size": "normal"
                },
            ]
        }
        client = FeishuClient(bot=bot)

        # 1为日程会议，2为即时会议，3为面试会议，4为开放平台会议，100为其他会议类型
        if meeting_source in [1, 2]:
            try:
                # 根据会议号获取会议ID
                meeting_url_response = client.get_meeting_list_by_no(meeting_no, start_time, end_time)
                if meeting_url_response.status_code == 200:
                    meeting_data = meeting_url_response.json()
                    if "data" in meeting_data and "meeting_briefs" in meeting_data['data'] and len(
                            meeting_data['data']['meeting_briefs']):
                        meeting_id = meeting_data['data']['meeting_briefs'][0]['id']
                    else:
                        raise Exception("no meeting id")
                else:
                    raise Exception("meeting api failed")
                logging.info(">>> meeting id: {}".format(meeting_id))
            except Exception as e:
                logging.error(">>> ERROR: {}".format(str(e)))
                card_content["elements"][1]["content"] = "**未查询到会议ID**"
                bot.send_card(open_id, card_content)
                continue

            try:
                # 根据会议ID获取会议录制文件
                count = 0
                allCount = 20
                record_url = None
                while count < allCount:
                    logging.info(">>> time {}".format(count + 1))
                    get_record_response = client.get_record(meeting_id)
                    if get_record_response.status_code == 200:
                        record_data = get_record_response.json()
                        if "data" in record_data:
                            record_url = record_data["data"]["recording"]["url"]
                            break
                    if count == allCount - 1:
                        break
                    logging.info(">>> no record, sleep {}".format(10 * (count + 1)))
                    time.sleep(10 * (count + 1))
                    count += 1

                if not record_url:
                    raise Exception("no record url")
                logging.info(">>> record url: {}".format(record_url))
            except Exception as e:
                logging.error(">>> ERROR: {}".format(str(e)))
                card_content["elements"][1]["content"] = "**未查询到录制文件**"
                bot.send_card(open_id, card_content)
                continue

            # 发送卡片消息
            card_content["elements"][1]["content"] = "录制文件（妙记）：[{}]({})".format(meeting_topic, record_url)
            card_resp = bot.send_card(open_id, card_content)
            message_id = card_resp.json()["data"]["message_id"]
            logging.info(">>> message resp: {}".format(card_resp.json()))
            logging.info(">>> message_id: {}".format(message_id))

            state_info = json.dumps({
                "message_id": message_id,
                "open_id": open_id,
                "meeting_id": meeting_id,
                "record_url": record_url,
                "start_time": start_time,
                "end_time": end_time,
            }, separators=(',', ':'))

            # 返回oauth授权地址
            scope = quote("minutes:minute:download minutes:minutes minutes:minutes:readonly")
            inner_oauth = f"{DOMAIN}/oauth/feishu?app_id={bot.app_id}&scope={scope}&state_dict={state_info}"
            feishu_url = f"{bot.host}/open-apis/authen/v1/authorize?app_id={bot.app_id}&redirect_uri={quote(inner_oauth)}&scope={scope}&state={bot.app_id}"
            oauth_url = f"{APPLINK_HOST}/client/web_url/open?mode=appCenter&url=" + quote(feishu_url)

            card_content["elements"].append(
                {
                    "tag": "action",
                    "actions": [
                        {
                            "tag": "button",
                            "text": {
                                "tag": "plain_text",
                                "content": "授权生成会议纪要"
                            },
                            "url": oauth_url,
                            "type": "primary",
                            "complex_interaction": True,
                            "width": "default",
                            "size": "medium"
                        }
                    ]
                }
            )

            card_resp1 = bot.update_card(message_id, card_content)
            logging.info(">>> card_resp1 code: {}".format(card_resp1.status_code))
            logging.info(">>> card_resp1 content: {}".format(card_resp1.content))
        else:
            card_content["elements"][1]["content"] = "**不支持的会议类型**"
            bot.send_card(open_id, card_content)
threading.Thread(target=meeting_handler, daemon=True).start()


oauth_queue = queue.Queue()
def oauth_handler():
    while True:
        bot, user_info = oauth_queue.get()
        logging.info("============================ oauth process")
        logging.info(">>> user_info: %r", user_info)

        client = FeishuClient(bot=bot)
        state_dict = json.loads(user_info["state_dict"])
        message_id = state_dict["message_id"]
        open_id = user_info["open_id"]
        record_url = state_dict["record_url"]
        meeting_id = state_dict["meeting_id"]
        start_time = state_dict["start_time"]
        end_time = state_dict["end_time"]

        try:
            # 获取会议详情
            meeting_detail_response = client.get_meeting(meeting_id)
            if meeting_detail_response.status_code == 200:
                meeting_detail = meeting_detail_response.json()
                if "data" in meeting_detail and "meeting" in meeting_detail['data']:
                    meeting_users = [i["id"] for i in meeting_detail["data"]["meeting"]["participants"]]
                    meeting_topic = meeting_detail["data"]["meeting"]["topic"]
                else:
                    raise Exception("no meeting detail")
            else:
                raise Exception("meeting detail api failed")
            logging.info(">>> meeting users: {}".format(meeting_users))
        except Exception as e:
            logging.error(">>> ERROR: {}".format(str(e)))
            bot.send_card(open_id, "未获取到会议详情")
            continue

        card_content = {
            "config": {},
            "header": {
                "title": {
                    "tag": "plain_text",
                    "content": meeting_topic + " - 智能纪要"
                },
                "template": "default"
            },
            "elements": [
                {
                    "tag": "note",
                    "elements": [
                        {
                            "tag": "plain_text",
                            "content": get_gmt_time(start_time, end_time)
                        }
                    ]
                },
                {
                    "tag": "markdown",
                    "content": "录制文件（妙记）：[{}]({})".format(meeting_topic, record_url),
                    "text_align": "left",
                    "text_size": "normal"
                },
                {
                    "tag": "action",
                    "actions": [
                        {
                            "tag": "button",
                            "text": {
                                "tag": "plain_text",
                                "content": "智能纪要生成中..."
                            },
                            "type": "primary",
                            "complex_interaction": True,
                            "width": "default",
                            "size": "medium"
                        }
                    ]
                }
            ]
        }
        bot.update_card(message_id, card_content)

        try:
            # 获取妙计文字记录
            count = 0
            allCount = 20
            file_obj = None
            minute_token = record_url.split("?")[0].split("minutes/")[-1]
            while count < allCount:
                logging.info(">>> time {}".format(count + 1))
                record_file_response = client.get_record_minute(minute_token, headers={
                    "Authorization": "Bearer {}".format(user_info['user_access_token']['access_token'])})
                if record_file_response.status_code == 200:
                    file_obj = record_file_response.text
                    break
                if count == allCount - 1:
                    break
                logging.info(">>> no record file, sleep {}".format(10 * (count + 1)))
                time.sleep(10 * (count + 1))
                count += 1

            if not file_obj:
                raise Exception("no record file")
            logging.info(">>> record file: {}".format(len(file_obj)))
        except Exception as e:
            logging.error(">>> ERROR: {}".format(str(e)))
            card_content["elements"][2]["actions"][0]["text"]["content"] = "未查询到录制文件内容"
            bot.update_card(message_id, card_content)
            continue

        try:
            # 获取妙计详情
            record_detail_resp = client.get_minute(minute_token, headers={
                "Authorization": "Bearer {}".format(user_info['user_access_token']['access_token'])})
            if record_detail_resp.status_code == 200:
                record_detail = record_detail_resp.json()
            else:
                raise Exception("record detail api failed")
            logging.info(">>> record detail: {}".format(record_detail))
        except Exception as e:
            logging.error(">>> ERROR: {}".format(str(e)))
            card_content["elements"][2]["actions"][0]["text"]["content"] = "未获取到妙计详情"
            bot.update_card(message_id, card_content)
            continue

        # 总结方案1: 通过大模型总结
        # summary = llm_model(file_obj)

        # 总结方案2: 通过调用飞书会议总结api
        try:
            # file_obj = """
            # 2024-08-24 15:19:33 CST|45分钟 6秒
            #
            # 关键词:
            # 软件产品设计、用户界面、功能需求、用户体验、性能优化、竞争分析
            #
            # 讲话人1
            # 大家好，今天我们主要讨论新软件产品的设计和功能需求。我先介绍一下我们的目标和方向。这款软件主要面向中小型企业，旨在提供高效的项目管理和团队协作工具。我们需要确保用户界面友好，功能强大且易于使用。
            #
            # 讲话人2
            # 是的，用户界面（UI）和用户体验（UX）的设计非常重要。我建议我们采用现代简洁的设计风格，避免过多的复杂元素。按钮和操作区域需要明显且易于点击，同时确保在不同设备上的兼容性。
            #
            # 讲话人3
            # 在功能方面，我们需要重点关注以下几个模块：项目管理、任务分配、团队沟通和文件共享。每个模块都需要有明确的操作流程，确保用户能够快速上手。此外，我们还需要考虑性能优化，确保在高负载情况下软件运行流畅。
            #
            # 讲话人4
            # 我这里有一些竞争对手的分析数据。我们主要的竞争对手有Trelo、Asana和Monday.com。它们各有优势，但也存在一些不足。我们可以借鉴它们的优点，同时避免它们的缺点。例如，Trelo的界面简洁但功能较少，Asana功能全面但界面复杂。我们需要找到一个平衡点。
            #
            # 讲话人5
            # 在测试方面，我们会分阶段进行功能测试和性能测试。首先是单元测试，确保每个功能模块都能正常运行；然后是集成测试，确保各个模块之间的交互没有问题；最后是性能测试，模拟高并发场景，确保系统的稳定性。
            #
            # 讲话人6
            # 作为客户代表，我想强调用户反馈的重要性。在产品上线之前，我们可以邀请一部分目标用户进行试用，并收集他们的反馈意见。这些反馈可以帮助我们优化产品，提升用户满意度。
            #
            # 讲话人1
            # 非常感谢大家的建议和意见。总结一下，我们需要在接下来的时间内完成以下任务：UI/UX设计师负责界面设计，开发团队负责功能开发和性能优化，测试团队制定测试计划，市场分析师继续进行竞争分析，客户代表准备用户试用计划。我们每周进行一次进度汇报，确保项目按计划推进。
            #
            # 讲话人2
            # 没问题，我会在下周之前提交初步的界面设计稿，供大家评审。
            #
            # 讲话人3
            # 我们会根据设计稿开始功能开发，并与UI/UX设计师保持密切沟通，确保设计与开发同步进行。
            #
            # 讲话人4
            # 我会继续收集和分析竞争对手的动态，并定期汇报给大家。
            #
            # 讲话人5
            # 我们会制定详细的测试计划，并在每个开发阶段进行相应的测试。
            #
            # 讲话人6
            # 我会联系一些潜在用户，邀请他们参与我们的试用计划，并准备收集反馈。
            #
            # 讲话人1
            # 好的，那今天的会议就到这里。谢谢大家的参与和贡献。我们下周同一时间再见。
            # """
            bbody = {
                "transcripts": [
                    {
                        "paragraph_id": 123,
                        "start_ms": 111,
                        "end_ms": 222,
                        "sentences": [
                            {
                                "sentence_id": 1234,
                                "content": file_obj,
                                "lang": "zh_cn",
                                "start_ms": 111,
                                "stop_ms": 222,
                            }
                        ]
                    }
                ],
                "duration": record_detail["data"]["minute"]["duration"],
                "topic": record_detail["data"]["minute"]["title"],
                "operator_id": record_detail["data"]["minute"]["owner_id"],
            }
            summary_task_resp = client.submit_summary_task(bbody,
                                    headers={"Authorization": "Bearer {}".format(
                                        user_info['user_access_token']['access_token'])})
            if summary_task_resp.status_code == 200:
                summary_task = summary_task_resp.json()
                task_id = summary_task["data"]["task_id"]
            else:
                raise Exception("submit summary task api failed")
            logging.info(">>> task_id: {}".format(task_id))
        except Exception:
            logging.error(">>> ERROR: {}".format(str(e)))
            card_content["elements"][2]["actions"][0]["text"]["content"] = "提交会议总结任务失败"
            bot.update_card(message_id, card_content)
            continue

        try:
            # 获取智能会议总结结果
            count = 0
            allCount = 20
            summary = None
            while count < allCount:
                logging.info(">>> time {}".format(count + 1))
                get_task_response = client.get_summary_task(task_id, headers={
                    "Authorization": "Bearer {}".format(user_info['user_access_token']['access_token'])})
                if get_task_response.status_code == 200:
                    task_data = get_task_response.json()
                    if "data" in task_data and task_data["code"] == 0:
                        summary = task_data["data"]
                        break
                if count == allCount - 1:
                    break
                logging.info(">>> no summary, sleep {}".format(10 * (count + 1)))
                time.sleep(10 * (count + 1))
                count += 1

            if not summary:
                raise Exception("no summary")
            logging.info(">>> summary: {}".format(summary))

            if "paragraph" in summary and "data" in summary["paragraph"]:
                summary_data = summary["paragraph"]["data"]
            else:
                summary_data = ""
            if not summary_data:
                card_content["elements"][2]["actions"][0]["text"]["content"] = "录制内容太短，未生成总结"
                bot.update_card(message_id, card_content)
                continue
        except Exception as e:
            logging.error(">>> ERROR: {}".format(str(e)))
            card_content["elements"][2]["actions"][0]["text"]["content"] = "未查询到智能总结结果"
            bot.update_card(message_id, card_content)
            continue

        try:
            # 创建云文档
            docx_body = {
                "title": meeting_detail["data"]["meeting"]["topic"] + " - 智能会议纪要",
            }
            docx_response = client.create_docx(docx_body, headers={"Authorization": "Bearer {}".format(
                                    user_info['user_access_token']['access_token'])})
            if docx_response.status_code == 200:
                docx_data = docx_response.json()
                document_id = docx_data["data"]["document"]["document_id"]
            else:
                raise Exception("create docx api failed")
            logging.info(">>> document_id: {}".format(document_id))
        except Exception:
            logging.error(">>> ERROR: {}".format(str(e)))
            card_content["elements"][2]["actions"][0]["text"]["content"] = "创建云文档失败"
            bot.update_card(message_id, card_content)
            continue

        try:
            # 创建块
            block_body = {
                "index": 0,  # 表示创建的块的索引
                "children": [
                    {
                        "block_type": 3,
                        "heading1": {
                            "elements": [
                                {
                                    "text_run": {
                                        "content": "会议信息",
                                        "text_element_style": {
                                            "bold": False,
                                            "inline_code": False,
                                            "italic": False,
                                            "strikethrough": False,
                                            "underline": False
                                        }
                                    }
                                }
                            ],
                            "style": {
                                "align": 1,
                                "folded": False
                            }
                        }
                    },
                    {
                        "block_type": 2,
                        "text": {
                            "elements": [
                                {
                                    "text_run": {
                                        "content": "会议主题：{}".format(meeting_detail["data"]["meeting"]["topic"]),
                                        "text_element_style": {
                                            "bold": False,
                                            "inline_code": False,
                                            "italic": False,
                                            "strikethrough": False,
                                            "underline": False
                                        }
                                    }
                                }
                            ],
                            "style": {
                                "align": 1,
                                "folded": False
                            }
                        }
                    },
                    {
                        "block_type": 2,
                        "text": {
                            "elements": [
                                {
                                    "text_run": {
                                        "content": "会议时间：{}".format(get_gmt_time(start_time, end_time)),
                                        "text_element_style": {
                                            "bold": False,
                                            "inline_code": False,
                                            "italic": False,
                                            "strikethrough": False,
                                            "underline": False
                                        }
                                    }
                                }
                            ],
                            "style": {
                                "align": 1,
                                "folded": False
                            }
                        }
                    },
                    {
                        "block_type": 2,
                        "text": {
                            "elements": [
                                {
                                    "text_run": {
                                        "content": "参会人：",
                                        "text_element_style": {
                                            "bold": False,
                                            "inline_code": False,
                                            "italic": False,
                                            "strikethrough": False,
                                            "underline": False
                                        }
                                    }
                                },
                            ],
                            "style": {
                                "align": 1,
                                "folded": False
                            }
                        }
                    },
                    {
                        "block_type": 3,
                        "heading1": {
                            "elements": [
                                {
                                    "text_run": {
                                        "content": "智能纪要",
                                        "text_element_style": {
                                            "bold": False,
                                            "inline_code": False,
                                            "italic": False,
                                            "strikethrough": False,
                                            "underline": False
                                        }
                                    }
                                }
                            ],
                            "style": {
                                "align": 1,
                                "folded": False
                            }
                        },
                    },
                    {
                        "block_type": 34,
                        "quote_container": {}
                    },
                    {
                        "block_type": 19,
                        "callout": {
                            "background_color": 5,
                            "emoji_id": "page_facing_up"
                        },
                    },
                ]
            }

            quote_container_block = {
                "index": 0,  # 表示创建的块的索引
                "children": [
                    {
                        "block_type": 2,
                        "text": {
                            "elements": [
                                {
                                    "text_run": {
                                        "content": "智能纪要依据会中总结内容生成，不代表平台立场，请谨慎甄别后使用",
                                        "text_element_style": {
                                            "bold": False,
                                            "inline_code": False,
                                            "italic": False,
                                            "strikethrough": False,
                                            "underline": False
                                        }
                                    }
                                }
                            ],
                            "style": {
                                "align": 1,
                                "folded": False
                            }
                        }
                    }
                ]
            }
            callout_block = {
                "index": 0,  # 表示创建的块的索引
                "children": [
                    {
                        "block_type": 4,
                        "heading2": {
                            "elements": [
                                {
                                    "text_run": {
                                        "content": "总结",
                                        "text_element_style": {
                                            "bold": True,
                                            "inline_code": False,
                                            "italic": False,
                                            "strikethrough": False,
                                            "underline": False
                                        }
                                    }
                                }
                            ],
                            "style": {
                                "align": 1,
                                "folded": False
                            }
                        },
                    },

                ],
            }

            # 添加总结内容block
            seqs = summary_data.strip().split("\n")
            for item in seqs:
                if not item.strip():
                    continue
                if item.startswith("- "):
                    if "**" in item:
                        item_list = item.split("**")
                        block = {
                            "block_type": 12,
                            "bullet": {
                                "elements": [
                                    {
                                        "text_run": {
                                            "content": item_list[1],
                                            "text_element_style": {
                                                "bold": True,
                                                "inline_code": False,
                                                "italic": False,
                                                "strikethrough": False,
                                                "underline": False
                                            }
                                        }
                                    },
                                ],
                                "style": {
                                    "align": 1,
                                    "folded": False
                                }
                            },
                        }
                        if len(item_list) >= 3:
                            for i in range(2, len(item_list)):
                                block["bullet"]["elements"].append(
                                    {
                                        "text_run": {
                                            "content": item_list[i],
                                            "text_element_style": {
                                                "bold": False,
                                                "inline_code": False,
                                                "italic": False,
                                                "strikethrough": False,
                                                "underline": False
                                            }
                                        }
                                    }
                                )
                    else:
                        block = {
                            "block_type": 12,
                            "bullet": {
                                "elements": [
                                    {
                                        "text_run": {
                                            "content": item.split("- ")[-1],
                                            "text_element_style": {
                                                "bold": False,
                                                "inline_code": False,
                                                "italic": False,
                                                "strikethrough": False,
                                                "underline": False
                                            }
                                        }
                                    },
                                ],
                                "style": {
                                    "align": 1,
                                    "folded": False
                                }
                            },
                        },

                    callout_block["children"].append(
                        block
                    )
                else:
                    callout_block["children"].append(
                        {
                            "block_type": 2,
                            "text": {
                                "elements": [
                                    {
                                        "text_run": {
                                            "content": item,
                                            "text_element_style": {
                                                "bold": False,
                                                "inline_code": False,
                                                "italic": False,
                                                "strikethrough": False,
                                                "underline": False
                                            }
                                        }
                                    }
                                ],
                                "style": {
                                    "align": 1,
                                    "folded": False
                                }
                            }
                        }
                    )

            # 添加参会人block
            for u in meeting_users:
                block_body["children"][3]["text"]["elements"].append(
                    {
                        "mention_user": {
                            "text_element_style": {
                                "bold": False,
                                "inline_code": False,
                                "italic": False,
                                "strikethrough": False,
                                "underline": False
                            },
                            "user_id": u
                        }
                    }
                )

            # 先创建page block下子块
            block_response = client.create_block(block_body, document_id=document_id, block_id=document_id, headers={"Authorization": "Bearer {}".format(
                                          user_info['user_access_token']['access_token'])})
            if block_response.status_code == 200:
                block_data = block_response.json()
            else:
                raise Exception("create block api failed")
            logging.info(">>> block_data: {}".format(block_data))
            time.sleep(1)

            # 再创建quote_container_block下子块
            quote_container_block_id = block_data["data"]["children"][5]["block_id"]
            quote_container_block_response = client.create_block(quote_container_block, document_id=document_id,
                                                                 block_id=quote_container_block_id,
                                                                 headers={"Authorization": "Bearer {}".format(
                                                                     user_info['user_access_token']['access_token'])})
            if quote_container_block_response.status_code == 200:
                quote_container_block_data = quote_container_block_response.json()
            else:
                raise Exception("create quote block api failed")
            logging.info(">>> quote_container_block_data: {}".format(quote_container_block_data))
            time.sleep(1)

            # 再创建callout_block下子块
            callout_block_id = block_data["data"]["children"][6]["block_id"]
            callout_block_response = client.create_block(callout_block, document_id=document_id, block_id=callout_block_id,
                                                 headers={"Authorization": "Bearer {}".format(
                                                     user_info['user_access_token']['access_token'])})
            if callout_block_response.status_code == 200:
                callout_block_data = callout_block_response.json()
            else:
                raise Exception("create callout block api failed")
            logging.info(">>> callout_block_data: {}".format(callout_block_data))
        except Exception:
            logging.error(">>> ERROR: {}".format(str(e)))
            card_content["elements"][2]["actions"][0]["text"]["content"] = "创建云文档block失败"
            bot.update_card(message_id, card_content)
            continue

        try:
            # 批量发送总结文档
            document_url = f"{FEISHU_HOST}/docx/{document_id}"
            bref_seqs = []
            bref = ""
            for item in seqs:
                if not item.strip():
                    continue
                if len(bref_seqs) == 3:
                    break
                bref_seqs.append(item)
                if not bref:
                    bref = item
                else:
                    bref = bref + " \n" + item
            bref = bref + " \n " + " ..."
            logging.info(">>> card bref: {}".format(bref))
            elements = [
                {
                    "tag": "note",
                    "elements": [
                        {
                            "tag": "plain_text",
                            "content": get_gmt_time(start_time, end_time)
                        }
                    ]
                },
                {
                    "tag": "markdown",
                    "content": bref,
                    "text_align": "left",
                    "text_size": "normal"
                },
                {
                    "tag": "action",
                    "actions": [
                        {
                            "tag": "button",
                            "text": {
                                "tag": "plain_text",
                                "content": "查看完整会议纪要"
                            },
                            "url": document_url,
                            "type": "primary",
                            "complex_interaction": True,
                            "width": "default",
                            "size": "medium"
                        }
                    ]
                }
            ]
            res_card_content = copy.deepcopy(card_content)
            res_card_content["elements"] = elements
            batch_url = f"{bot.host}/open-apis/message/v4/batch_send/"
            meeting_users.remove(open_id)
            if meeting_users:
                message_body = {
                    "open_ids": meeting_users,
                    # "open_ids": [open_id],
                    "msg_type": "interactive",
                    "card": res_card_content
                }
                batch_response = bot.post(batch_url, data=json.dumps(message_body)).json()
                # print(">>> batch_response: ", batch_response)
                logging.info(">>> batch_response: {}".format(batch_response))
        except Exception:
            logging.error(">>> ERROR: {}".format(str(e)))
            card_content["elements"][2]["actions"][0]["text"]["content"] = "批量发送总结文档失败"
            bot.update_card(message_id, card_content)
            continue

        bot.update_card(message_id, res_card_content)
        oauth_queue.task_done()
threading.Thread(target=oauth_handler, daemon=True).start()


@hook.on_bot_message(bot=bot, event_type="vc.meeting.all_meeting_ended_v1")
def on_event_meeting_listen(bot, event_id, event, *args, **kwargs):
    meeting_queue.put((event_id, event, bot))


@oauth.on_bot_event(event_type="oauth:user_info", bot=bot)
def on_oauth_user_info(bot, event_id, user_info, *args, **kwargs):
    oauth_queue.put((bot, user_info))


@hook.on_bot_message(message_type="text", bot=bot)
def on_text_message(bot, message_id, content, *args, **kwargs):
    text = content["text"]
    print("reply_text", message_id, text)
    bot.reply_text(message_id, "reply: " + text)


def get_gmt_time(start_ts, end_ts):
    # 将时间戳转换为datetime对象
    start_dt_object = datetime.datetime.fromtimestamp(int(start_ts), tz=datetime.timezone(datetime.timedelta(hours=8)))
    end_dt_object = datetime.datetime.fromtimestamp(int(end_ts), tz=datetime.timezone(datetime.timedelta(hours=8)))

    # 映射星期几的英文缩写到中文
    weekdays = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
    weekday_chinese = weekdays[start_dt_object.weekday()]

    start_time_str = start_dt_object.strftime('%m月%d号（{}） %H:%M'.format(weekday_chinese))
    end_time_str = end_dt_object.strftime('%H:%M')

    # 将datetime对象格式化为GMT字符串时间
    result_str = f"{start_time_str} - {end_time_str} GMT+08"
    return result_str


app = oauth.get_app()
app.register_blueprint(hook.get_blueprint())


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8888)
