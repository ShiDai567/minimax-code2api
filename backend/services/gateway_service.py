"""OpenAI Chat / Responses <-> Anthropic Messages. Unsupported fields are rejected, never dropped."""
import json
import time
import uuid

from common.problems import ApiProblem

CHAT_FIELDS = {"model", "messages", "max_tokens", "max_completion_tokens", "temperature", "top_p", "stream", "stop"}
RESPONSE_FIELDS = {"model", "input", "instructions", "max_output_tokens", "temperature", "top_p", "stream"}


def to_anthropic(body, protocol):
    if protocol == "anthropic":
        return body
    allowed = CHAT_FIELDS if protocol == "openai_chat" else RESPONSE_FIELDS
    unsupported = set(body) - allowed
    if unsupported:
        raise ApiProblem("Unsupported fields: " + ", ".join(sorted(unsupported)), 400, "UNSUPPORTED")
    if protocol == "openai_chat":
        messages = body.get("messages")
    else:
        incoming = body.get("input")
        messages = [{"role": "user", "content": incoming}] if isinstance(incoming, str) else incoming
        if body.get("instructions") is not None:
            messages = [{"role": "system", "content": body["instructions"]}] + (messages if isinstance(messages, list) else [])
    if not isinstance(messages, list) or not messages:
        raise ApiProblem("A non-empty message list is required", 400)
    converted, system = [], []
    for item in messages:
        if not isinstance(item, dict) or set(item) - {"role", "content"} or not isinstance(item.get("content"), str):
            raise ApiProblem("Only plain-text messages are supported", 400, "UNSUPPORTED")
        if item["role"] in ("system", "developer"):
            system.append(item["content"])
        elif item["role"] in ("user", "assistant"):
            converted.append({"role": item["role"], "content": item["content"]})
        else:
            raise ApiProblem("Unsupported message role", 400, "UNSUPPORTED")
    if not converted:
        raise ApiProblem("A user or assistant message is required", 400)
    maximum = body.get("max_tokens", body.get("max_completion_tokens", body.get("max_output_tokens", 4096)))
    if type(maximum) is not int or maximum < 1:
        raise ApiProblem("Invalid maximum output tokens", 400)
    result = {"model": body.get("model"), "messages": converted, "max_tokens": maximum}
    if system:
        result["system"] = "\n\n".join(system)
    for field in ("temperature", "top_p"):
        if field in body:
            result[field] = body[field]
    if "stop" in body:
        stop = body["stop"]
        stop = [stop] if isinstance(stop, str) else stop
        if not isinstance(stop, list) or not all(isinstance(item, str) for item in stop):
            raise ApiProblem("Invalid stop sequences", 400)
        result["stop_sequences"] = stop
    if body.get("stream") is True:
        result["stream"] = True
    return result


def from_anthropic(body, protocol):
    if protocol == "anthropic":
        return body
    if not isinstance(body, dict) or not isinstance(body.get("content"), list):
        raise ApiProblem("Invalid upstream message", 502, "UPSTREAM_ERROR")
    if any(not isinstance(block, dict) or block.get("type") != "text" or not isinstance(block.get("text"), str) for block in body["content"]):
        raise ApiProblem("Upstream returned unsupported content", 502, "UNSUPPORTED")
    content = "".join(block["text"] for block in body["content"])
    usage = body.get("usage") if isinstance(body.get("usage"), dict) else {}
    incoming, outgoing = usage.get("input_tokens", 0), usage.get("output_tokens", 0)
    if type(incoming) is not int or type(outgoing) is not int or incoming < 0 or outgoing < 0:
        raise ApiProblem("Invalid upstream usage", 502, "UPSTREAM_ERROR")
    if body.get("stop_reason") not in ("end_turn", "stop_sequence", "max_tokens", None):
        raise ApiProblem("Unsupported upstream stop reason", 502, "UNSUPPORTED")
    identifier = body.get("id") or "msg_" + uuid.uuid4().hex
    model = body.get("model")
    created = int(time.time())
    finish = "length" if body.get("stop_reason") == "max_tokens" else "stop"
    if protocol == "openai_chat":
        return {
            "id": identifier,
            "object": "chat.completion",
            "created": created,
            "model": model,
            "choices": [{"index": 0, "message": {"role": "assistant", "content": content}, "finish_reason": finish}],
            "usage": {"prompt_tokens": incoming, "completion_tokens": outgoing, "total_tokens": incoming + outgoing},
        }
    status = "incomplete" if finish == "length" else "completed"
    return {
        "id": identifier,
        "object": "response",
        "created_at": created,
        "status": status,
        "model": model,
        "incomplete_details": {"reason": "max_output_tokens"} if status == "incomplete" else None,
        "output": [
            {
                "id": "msg_" + uuid.uuid4().hex,
                "type": "message",
                "status": "completed",
                "role": "assistant",
                "content": [{"type": "output_text", "text": content, "annotations": []}],
            }
        ],
        "usage": {"input_tokens": incoming, "output_tokens": outgoing, "total_tokens": incoming + outgoing},
    }


def anthropic_sse_to_openai(chunk: bytes, protocol: str, state: dict):
    """Convert one upstream SSE chunk. Yields zero or more already-encoded SSE frames."""
    text = chunk.decode("utf-8", errors="replace")
    frames = []
    for block in text.split("\n\n"):
        if not block.strip():
            continue
        event, data = "message", ""
        for line in block.split("\n"):
            if line.startswith("event:"):
                event = line[6:].strip()
            elif line.startswith("data:"):
                data = line[5:].strip()
        if not data:
            continue
        try:
            payload = json.loads(data)
        except ValueError:
            continue
        if event == "message_start":
            message = payload.get("message") if isinstance(payload, dict) else {}
            state["id"] = (message or {}).get("id") or "chatcmpl_" + uuid.uuid4().hex
            state["model"] = (message or {}).get("model")
            state["created"] = int(time.time())
            frames.append(_chunk(state, {"role": "assistant", "content": ""}, None))
        elif event == "content_block_delta":
            delta = payload.get("delta") if isinstance(payload, dict) else {}
            if isinstance(delta, dict) and isinstance(delta.get("text"), str):
                frames.append(_chunk(state, {"content": delta["text"]}, None))
        elif event == "message_delta":
            delta = payload.get("delta") if isinstance(payload, dict) else {}
            reason = delta.get("stop_reason") if isinstance(delta, dict) else None
            finish = "length" if reason == "max_tokens" else "stop"
            frames.append(_chunk(state, {}, finish))
            if protocol == "openai_chat":
                frames.append(b"data: [DONE]\n\n")
        elif event == "message_stop" and protocol == "openai_responses":
            frames.append(_response_done(state))
        elif event == "error":
            raise ApiProblem("Upstream stream failed", 502, "UPSTREAM_ERROR")
    return frames


def _chunk(state, delta, finish):
    body = {
        "id": state.get("id") or "chatcmpl_pending",
        "object": "chat.completion.chunk",
        "created": state.get("created") or int(time.time()),
        "model": state.get("model"),
        "choices": [{"index": 0, "delta": delta, "finish_reason": finish}],
    }
    return f"data: {json.dumps(body, ensure_ascii=False)}\n\n".encode()


def _response_done(state):
    body = {"type": "response.completed", "response": {"id": state.get("id"), "model": state.get("model"), "status": "completed"}}
    return f"data: {json.dumps(body, ensure_ascii=False)}\n\n".encode()
