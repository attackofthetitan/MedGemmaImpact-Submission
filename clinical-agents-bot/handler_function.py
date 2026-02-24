import os
import sys
import json
import httpx

from linebot.v3.webhook import WebhookParser
from linebot.v3.messaging import (
    AsyncApiClient,
    AsyncMessagingApi,
    Configuration,
    ReplyMessageRequest,
    PushMessageRequest,
    TextMessage,
)
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.webhooks import (
    FollowEvent,
    JoinEvent,
    MessageEvent,
    TextMessageContent,
    ImageMessageContent,
    FollowEvent,
    LeaveEvent,
    MemberJoinedEvent,
    MemberLeftEvent,
)
from linebot.v3 import WebhookHandler
from starlette.responses import FileResponse

import bind_controller
from config import config
from bot_controller import Bot_Controller
from auth_controller import Auth_Controller
from bind_controller import Bind_Controller

async def handle_message(
    event: MessageEvent,
    auth_controller: Auth_Controller,
    controller: Bot_Controller,
    line_bot_api: AsyncMessagingApi,
    bind_controller: Bind_Controller,
):
    is_group: bool = event.source.type == "group"
    group_id: str | None = None
    input_id: str = event.source.user_id
    # print(f"{is_group} {input_id}")
    if is_group:
        print("received message from group")
        group_id = event.source.group_id
        input_id = group_id
    bind_code = await bind_controller.is_binding_msg(event.message.text)
    if bind_code:
        bot_token = await auth_controller.get_token()
        bind_res, bind_status = await bind_controller.bind_account(
            input_id, event.message.text, bot_token
        )
        if bind_status == 200 and bind_res:
            reply_text = f"綁定成功"
        else:
            detail = (bind_res or {}).get("detail")
            if isinstance(detail, dict):
                reply_text = f"綁定失敗：{detail.get('message', 'unknown error')}"
            else:
                reply_text = f"綁定失敗：{detail or 'unknown error'}"
        await line_bot_api.reply_message(
            ReplyMessageRequest(
                reply_token=event.reply_token,
                messages=[TextMessage(text=reply_text)],
            )
        )
        return
    is_staff = await auth_controller.is_staff(input_id)
    if is_staff:
        is_review,review_res = controller.is_review_msg(event.message.text)
        if is_review:
            res = await handle_review(input_id=review_res.get("patient_id"),target="patient",review_response=review_res,
            controller=controller,auth_controller=auth_controller,line_bot_api=line_bot_api,session_id=review_res.get("session_id"))
            if res:
                reply = res.get("reply")
                await line_bot_api.reply_message(
                    ReplyMessageRequest(
                        reply_token=event.reply_token,
                        messages=[TextMessage(text=reply)],
                    )
                )
            return
        is_reply,reply_res = controller.is_reply_approved_msg(event.message.text)
        if is_reply and reply_res.get("approved"):
            await handle_send_relpy(
                input_id=reply_res.get("patient_id"),
                session_id=reply_res.get("session_id"),
                line_bot_api=line_bot_api,
                auth_controller=auth_controller,
                controller=controller,
            )
            reply = "已回覆"
            await line_bot_api.reply_message(
                ReplyMessageRequest(
                    reply_token=event.reply_token,
                    messages=[TextMessage(text=reply)],
                )
            )
            return
        elif is_reply and not reply_res.get("approved"):
            reply = "已拒絕回覆，您隨時可以用上述格式重新回覆，或是用上述審核格式重新審核。"
            await line_bot_api.reply_message(
                ReplyMessageRequest(
                    reply_token=event.reply_token,
                    messages=[TextMessage(text=reply)],
                )
            )
            return

    print("handling message event")
    token = await auth_controller.get_token()
    patient_id = await auth_controller.get_patient(input_id)
    res = await controller.process_query(
        query=event.message.text, patient_id=patient_id, input_id=input_id, token=token
    )
    print(f"process_query returned: {res}")

    if res.get("reply"):
        await line_bot_api.reply_message(
            ReplyMessageRequest(
                reply_token=event.reply_token,
                messages=[
                    TextMessage(
                        text=res.get(
                            "reply", "Sorry, I cannot process your request right now."
                        )
                    )
                ],
            )
        )
    if res.get("need_push"):
        res = await handle_send(
            input_id,
            res.get("target", {}),
            res.get("data"),
            line_bot_api=line_bot_api,
            auth_controller=auth_controller,
            controller=controller,
            status=res.get("status"),
        )


async def handle_review(
    input_id: str,
    controller: Bot_Controller,
    auth_controller: Auth_Controller,
    line_bot_api: AsyncMessagingApi,
    target: str,
    review_response: dict,
    session_id: str,
):
    token = await auth_controller.get_token()
    res = await controller.process_review(session_id,review_response,token)
    patient_id = input_id
    if res.get("status") == "needs_revision":
        template = f"session：{session_id}\n回覆：同意/不同意\n病患：{patient_id}\n醫生註記：若無請填無"
        reply = f"需要您重新審核：\n請按照以下格式回覆：\n{template}"
        return {
            "reply": reply,
        }
    elif res.get("status") == "ready_to_send":
        draft = res.get("reply")
        field_keys = [
            "acknowledgment", 
            "understanding", 
            "response", 
            "action_items", 
            "warning_signs", 
            "follow_up",
            "emergency_info"
        ]
        segments = []
        greeting = draft.get("greeting")
        if greeting:
            segments.append(f"{greeting}\n")
        for key in field_keys:
            value = draft.get(key)
            if not value:
                continue
            
            if isinstance(value, list):
                segments.append("\n".join(value))
            else:
                segments.append(str(value))
        response = "\n".join(segments).strip()
        reply = f"以下訊息將會回覆給病患：\n{response}，請問您是否同意，請照以下格式回覆:\n病患：{patient_id}\nsession：{session_id}\n傳送回覆：同意/不同意"
        return {
            # "need_push": True,
            "reply": reply,
        }
    elif res.get("status") == "escalated":
        patient_id = input_id
        template = f"session：{session_id}\n病患：{patient_id}"
        reply = f"請您手動處理：\n{template}"
        return {
            "reply": reply,
        }

async def handle_send_relpy(
    input_id: str,
    session_id: str,
    line_bot_api: AsyncMessagingApi,
    auth_controller: Auth_Controller,
    controller: Bot_Controller,
):
    platform_id = await auth_controller.get_patient_platform_id(input_id)
    token = await auth_controller.get_token()
    res = await controller.process_send_reply(session_id, token)
    draft = res.get("reply")
    field_keys = [
        "acknowledgment", 
        "understanding", 
        "response", 
        "action_items", 
        "warning_signs", 
        "follow_up",
        "emergency_info"
    ]
    segments = []
    greeting = draft.get("greeting")
    if greeting:
        segments.append(f"{greeting}\n")
    for key in field_keys:
        value = draft.get(key)
        if not value:
            continue
        
        if isinstance(value, list):
            segments.append("\n".join(value))
        else:
            segments.append(str(value))
    response = "\n".join(segments).strip()
    if response and platform_id:
        await line_bot_api.push_message(
            PushMessageRequest(
                to=platform_id,
                messages=[TextMessage(text=response)],
            )
        )
        return {
            "status": "success",
        }
    else:
        return {
            "status": "fail",
        }

async def handle_send(
    input_id: str,
    target: str,
    data: dict,
    status: str,
    line_bot_api: AsyncMessagingApi,
    auth_controller: Auth_Controller,
    controller: Bot_Controller,
):
    if not target or not data or not status:
        return {
            "status": "fail",
        }
    patient_id = data.get("patient_id")
    patient_info = await auth_controller.get_patient_info(patient_id)
    patient_info = patient_info if patient_info else {}
    staff = await auth_controller.get_staff(input_id, patient_id)
    if status == "emergency":
        print(f"emergency: {patient_id}")
        reply = f"病患{patient_id} {patient_info.get('name')} 遇到緊急狀況，請立即處理"

    elif status == "need_review":
        patient_id = (
            patient_id if patient_id else await auth_controller.get_patient(input_id)
        )
        template = f"session：{data.get("session_id")}\n回覆：同意/不同意\n病患：{patient_id}\n醫生註記：若無請填無"
        reply = f"需要您協助處理：\n病患{patient_id} {patient_info.get('name')}\n{data.get('ticket').get('case_card').get('summary')}\n您是否同意本機器人傳送回覆給病人，請按照以下格式回覆:\n{template}"
    elif status == "need_manual_review":
        reply = f"需要您人工審核 session：{data.get("session_id")}"
    else:
        return {
            "status": "fail",
        }

    if to_id := staff.get(target,auth_controller.get_default_staff()):
        await line_bot_api.push_message(
            PushMessageRequest(
                to=to_id,
                messages=[TextMessage(text=reply)],
            )
        )


async def handle_image(event: MessageEvent, line_bot_api: AsyncMessagingApi):
    isGroup: bool = event.source.type == "group"
    groupId: str | None = None
    if isGroup:
        groupId = event.source.group_id
    print("handling message event")
    # todos: implement actual chatbot logic here

    await line_bot_api.reply_message(
        ReplyMessageRequest(
            reply_token=event.reply_token,
            messages=[TextMessage(text="這個功能目前無法使用")],
        )
    )


async def handle_bot_join():
    pass


async def handle_bot_leave():
    pass


async def handle_user_join():
    pass


async def handle_follow(event: FollowEvent, line_bot_api: AsyncMessagingApi):
    await line_bot_api.reply_message(
        ReplyMessageRequest(
            reply_token=event.reply_token,
            messages=[TextMessage(text="hello")],
        )
    )