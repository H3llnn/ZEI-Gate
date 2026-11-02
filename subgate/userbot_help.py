"""Master bot inline help; every button is bound to the account owner."""
import html
from zei_userbot.runtime import CATEGORIES
from zei_userbot.state import State
from .service import inline


def screen(owner, prefix, category=None, helper=""):
    h = html.escape
    text = f"✦ <b>ZΞI Userbot</b>\nSemua kendali ada di tanganmu.\nPrefix: <code>{h(prefix)}</code>\n\n"
    if category in CATEGORIES:
        text += "\n".join(f"<code>{h(prefix+k)}</code> · {h(v)}" for k,v in CATEGORIES[category].items()) + "\n\n"
    else:
        text += "Pilih kategori untuk menjelajahi fitur.\n\n"
    text += "<i>Maintained by Zeisss</i>"
    buttons = [[{"text": name.title(), "callback_data": f"uh:{owner}:{name}"}] for name in CATEGORIES]
    if helper: buttons += [[{"text":"⚙️ Ubah Prefix", "url":f"https://t.me/{helper}?start=uprefix"}]]
    return text, inline(buttons)


async def handle(ui, update):
    query = update.get("inline_query")
    callback = update.get("callback_query")
    item = query or callback
    owner = item["from"]["id"]
    service = getattr(ui.manager, "userbots", None)
    allowed = bool(service and owner in service.running and ui.db.allowed(owner,"userbot"))
    if query:
        results = []
        if allowed and query.get("query") == "zei-help":
            state = State(service.directory / str(owner) / "settings.sqlite")
            try: text, buttons = screen(owner,state.prefix,helper=service.helper)
            finally: state.close()
            results = [{"type":"article", "id":"zei-help", "title":"✦ ZΞI Userbot", "input_message_content":{"message_text":text,"parse_mode":"HTML"},"reply_markup":buttons}]
        await ui.api.call("answerInlineQuery",inline_query_id=query["id"],results=results,cache_time=0,is_personal=True)
        return
    parts = callback.get("data", "").split(":")
    if len(parts) != 3 or not parts[1].isdigit() or int(parts[1]) != owner or not allowed:
        await ui.api.call("answerCallbackQuery",callback_query_id=callback["id"],text="Menu ini hanya untuk pemilik akun yang masih memiliki izin.",show_alert=True)
        return
    await ui.api.call("answerCallbackQuery",callback_query_id=callback["id"])
    state = State(service.directory / str(owner) / "settings.sqlite")
    try: text, buttons = screen(owner,state.prefix,parts[2],service.helper)
    finally: state.close()
    if callback.get("inline_message_id"):
        await ui.api.call("editMessageText",inline_message_id=callback["inline_message_id"],text=text,parse_mode="HTML",reply_markup=buttons)
