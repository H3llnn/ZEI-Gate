"""Master bot inline help; every button is bound to the account owner."""
import html
from zei_userbot.runtime import CATEGORIES
from zei_userbot.state import State
from .service import inline


EXAMPLES = {
    'ping': 'ping', 'id': 'id', 'help': 'help',
    'save': 'save belanja', 'notes': 'notes', 'get': 'get belanja', 'delnote': 'delnote belanja',
    'purge': 'purge', 'say': 'say Halo semua', 'afk': 'afk Sedang makan', 'unafk': 'unafk',
    'prefix': 'prefix !', 'status': 'status', 'whois': 'whois @username',
    'setname': 'setname Zeisss', 'setbio': 'setbio Selamat datang', 'stats': 'stats',
    'ban': 'ban @username', 'unban': 'unban @username', 'kick': 'kick @username',
    'pin': 'pin', 'unpin': 'unpin', 'promote': 'promote @username', 'demote': 'demote @username',
    'invite': 'invite @username', 'title': 'title Grup Kita', 'chatinfo': 'chatinfo',
    'hash': 'hash Halo', 'time': 'time', 'calc': 'calc (2 + 3) * 4', 'getlink': 'getlink',
    'filter': 'filter halo | Halo juga!', 'filters': 'filters', 'delfilter': 'delfilter halo',
    'welcome': 'welcome Selamat datang, {nama}!', 'pmpermit': 'pmpermit on',
    'approve': 'approve @username', 'disapprove': 'disapprove @username',
}

USAGE = {
    'save': 'Balas pesan teks yang ingin disimpan, lalu kirim perintah dengan nama catatan (maks. 40 karakter).',
    'purge': 'Balas pesan awal untuk menghapus rentang sampai perintah ini, maksimal 100 pesan milikmu.',
    'pin': 'Di grup/channel dengan izin yang sesuai, balas pesan yang ingin disematkan.',
    'unpin': 'Di grup/channel, balas pesan untuk melepas sematannya; tanpa balasan melepas semua sematan.',
    'promote': 'Di grup/channel dengan izin admin, balas anggota atau masukkan username untuk menjadikan admin.',
    'demote': 'Di grup/channel dengan izin admin, balas anggota atau masukkan username untuk mencabut admin.',
    'getlink': 'Balas pesan di grup/channel untuk mengambil link pesan.',
    'welcome': 'Jalankan di grup/channel. Gunakan {nama} untuk nama anggota; welcome off mematikan sambutan.',
    'pmpermit': 'Gunakan on/off. Akun asing mendapat pemberitahuan; tidak diblokir otomatis.',
    'calc': 'Gunakan angka, tanda kurung, dan operator + - * / // % (tanpa pangkat atau kode).',
}


def screen(owner, prefix, category=None, helper="", command=None):
    h = html.escape
    text = "✦ <b>ZΞI Userbot</b>"
    if category in CATEGORIES and command in CATEGORIES[category]:
        text += f"\n\n<b>{h(command)}</b> · {h(CATEGORIES[category][command])}"
        if command in USAGE: text += "\n" + h(USAGE[command])
        if category == 'admin' and command not in ('pin', 'unpin', 'promote', 'demote'):
            text += '\nJalankan di grup/channel dengan izin yang sesuai.'
        text += f"\n\nContoh:\n<code>{h(prefix + EXAMPLES[command])}</code>"
        buttons = [[{'text': '← Kembali', 'callback_data': f'uh:{owner}:{category}'}]]
    elif category in CATEGORIES:
        text += f" · {h(category.title())}"
        buttons = [[{'text': name, 'callback_data': f'uh:{owner}:{category}:{name}'}] for name in CATEGORIES[category]]
    else:
        buttons = [[{"text": name.title(), "callback_data": f"uh:{owner}:{name}"}] for name in CATEGORIES]
    if category in CATEGORIES: buttons += [[{'text': '⌂ Beranda', 'callback_data': f'uh:{owner}:home'}]]
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
    valid = (len(parts) == 3 and (parts[2] in CATEGORIES or parts[2] == 'home')) or (len(parts) == 4 and parts[2] in CATEGORIES and parts[3] in CATEGORIES[parts[2]])
    if not valid or parts[0] != 'uh' or not parts[1].isdigit() or int(parts[1]) != owner or not allowed:
        await ui.api.call("answerCallbackQuery",callback_query_id=callback["id"],text="Menu ini hanya untuk pemilik akun yang masih memiliki izin.",show_alert=True)
        return
    await ui.api.call("answerCallbackQuery",callback_query_id=callback["id"])
    state = State(service.directory / str(owner) / "settings.sqlite")
    try: text, buttons = screen(owner,state.prefix,parts[2],service.helper,parts[3] if len(parts) == 4 else None)
    finally: state.close()
    if callback.get("inline_message_id"):
        await ui.api.call("editMessageText",inline_message_id=callback["inline_message_id"],text=text,parse_mode="HTML",reply_markup=buttons)
