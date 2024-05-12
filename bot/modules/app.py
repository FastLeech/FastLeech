import requests
from swibots import *
from swibots import Message
from psutil import virtual_memory, cpu_percent, disk_usage
from inspect import iscoroutinefunction
from datetime import datetime
from bot import appTaskHolder, DOWNLOAD_DIR, botStartTime
from time import time
from random import randint
import asyncio
from builtins import filter
from bot.helper.ext_utils.status_utils import (
    get_progress_bar_string,
    get_readable_file_size,
    getAllTasks,
    getTaskByGid,
    getSpecificTasks,
    sync_to_async,
    get_readable_time,
)
from bot import bot, LOGGER, config_dict, task_dict, task_dict_lock, DATABASE_URL
from bot.helper.ext_utils.db_handler import DbManager
from bot.helper.switch_helper.bot_commands import BotCommands
from bot.helper.mirror_leech_utils.status_utils.aria2_status import Aria2Status
from bot.helper.switch_helper.filters import CustomFilters
from bot.helper.ext_utils.status_utils import get_readable_file_size
from psutil import virtual_memory, cpu_percent, disk_usage


bot.app_bar = AppBar(
    title="Leech X",
    left_icon="https://f004.backblazeb2.com/file/switch-bucket/30e0ded9-0edc-11ef-9e61-d41b81d4a9f0.png",
    secondary_icon="https://f004.backblazeb2.com/file/switch-bucket/43afabf4-0edc-11ef-b248-d41b81d4a9f0.png",
)


def parseYTDL_SUPPORTED():
    siteNames = []
    addedNames = []
    for line in (
        requests.get(
            "https://raw.githubusercontent.com/yt-dlp/yt-dlp/master/supportedsites.md"
        )
        .content.decode()
        .split("\n")[1:]
    ):
        line = line[2:].replace("**", "").strip()
        if ":" in line:
            tag = line.split(":")[0]
            if tag in addedNames:
                continue
            addedNames.append(tag)
            line = tag
        siteNames.append(line)
    return set(siteNames)


SUPPORTED_SITES = parseYTDL_SUPPORTED()

appConf = {}
editTask = {}


def stopTask(user):
    print("stopping", user, 44)
    if editTask.get(user):
        editTask[user].cancel()
        del editTask[user]


def getBottomBar(page: str):
    return BottomBar(
        options=[
            BottomBarTile(
                tile,
                callback_data=data.get("clb", tile),
                selected=tile == page,
                icon=data.get("icon"),
                selection_icon=data.get("selected"),
            )
            for tile, data in {
                "Home": {
                    "clb": "Home|self",
                    "selected": "https://f004.backblazeb2.com/file/switch-bucket/3f0b3c14-0edc-11ef-97a0-d41b81d4a9f0.png",
                    "icon": "https://f004.backblazeb2.com/file/switch-bucket/41c8da8a-0edc-11ef-ac63-d41b81d4a9f0.png",
                },
                "Downloader": {
                    "selected": "https://f004.backblazeb2.com/file/switch-bucket/2ec17226-0edc-11ef-989c-d41b81d4a9f0.png",
                    "icon": "https://f004.backblazeb2.com/file/switch-bucket/2cc37109-0edc-11ef-92b0-d41b81d4a9f0.png",
                },
                "History": {
                    "icon": "https://f004.backblazeb2.com/file/switch-bucket/45ef59f2-0edc-11ef-b5f2-d41b81d4a9f0.png",
                    "selected": "https://f004.backblazeb2.com/file/switch-bucket/4965825b-0edc-11ef-abb6-d41b81d4a9f0.png",
                },
            }.items()
        ]
    )


async def manageUpdatePage(
    ctx: BotContext[CallbackQueryEvent], callback=None, start=True
):
    user = ctx.event.action_by_id

    stopTask(user)

    async def edit_screen():
        while editTask.get(user):
            if callback:
                ctx.event.callback_data = callback
            if "detail|" in ctx.event.callback_data:
                await leechDetailPage(ctx, fs=False)
            else:
                await onHome(ctx, fs=False)
            await asyncio.sleep(5)

    if start:
        print(ctx.event.callback_data, "updating")
        task = asyncio.create_task(edit_screen())
        editTask[user] = task


async def onHome(ctx: BotContext[CallbackQueryEvent], from_app=False, fs=True):
    taskList = []
    CLB = ctx.event.callback_data

    Downloader = False
    if "Downloader" in CLB:
        Downloader = True
        page_clb = "Downloader"
    else:
        page_clb = "Home"

    comps = []
    if "|" not in CLB or not CLB.startswith(("Home", "Downloader")):
        CLB = f"{page_clb}|self"

    userId = ctx.event.action_by_id
    uconf = appConf.get(userId, {})
    #    if not uconf:
    #        uconf[userId] = {}
    #    uconf[userId]["page"] = CLB

    userOnly = "|self" in CLB

    comps = [
        CardView(
            card_size=CardSize.SMALL,
            horizontal=True,
            cards=[
                Card(
                    title="*Free*",
                    subtitle2=f"{get_readable_file_size(disk_usage(DOWNLOAD_DIR).free)}",
                    cardType="METRICS",
                ),
                Card(
                    title="*Uptime*",
                    subtitle2=f"{get_readable_time(time() - botStartTime)}",
                    cardType="METRICS",
                ),
                Card(
                    title="*RAM/CPU*",
                    subtitle2=f"{virtual_memory().percent}%",
                    cardType="METRICS",
                ),
            ],
        )
    ]
    if Downloader:
        comps.extend(
            [
                Text("*Supported Sites*"),
                Button("Tap to View", callback_data="viewList"),
            ]
        )
    comps.append(
        TextInput(
            label="",
            placeholder="Paste torrent or magnet link",
            callback_data="onLinkEnter",
            multiline=True,
        ),
    )
    if not Downloader:
        comps.extend(
            [
                Dropdown(
                    options=[
                        ListItem("Mirror", callback_data="select+Mirror"),
                        ListItem("Leech", callback_data="select+Leech"),
                    ],
                    placeholder=(
                        f"Mode: {uconf['mode']}" if uconf.get("mode") else "Select mode"
                    ),
                ),
                Dropdown(
                    placeholder=(
                        f"Engine: {uconf['engine']}"
                        if uconf.get("engine")
                        else "Select Engine"
                    ),
                    options=[
                        ListItem("Aria", callback_data="engine|Aria"),
                        ListItem("QbitTorrent", callback_data="engine|Qbitorrent"),
                    ],
                ),
            ]
        )
    comps.extend(
        [
            Button(
                "Start task",
                callback_data="startDownloadTask" if Downloader else "startTask",
            ),
            Text("Ongoing Tasks", TextSize.SMALL),
            ButtonGroup(
                [
                    Button(
                        Text(text, color="#ffffff" if clb == CLB else "#c9c6bd"),
                        callback_data=clb,
                        color="#2F80ED" if clb == CLB else "#000000",
                    )
                    for text, clb in {
                        "Your tasks": f"{page_clb}|self",
                        "Other tasks": f"{page_clb}|other",
                    }.items()
                ]
            ),
        ]
    )
    #    await ctx.event.answer(callback=AppPage(
    #       components=comps
    #  ))

    if userOnly:
        tasks = await sync_to_async(getSpecificTasks, "All", ctx.event.action_by_id)
    else:
        tasks = await getAllTasks("All", None)
        tasks = list(filter(lambda task: task.listener.userId != userId, tasks))

    for task in tasks:
        task: Aria2Status
        progress = (
            await task.progress()
            if iscoroutinefunction(task.progress)
            else task.progress()
        )

        listener = task.listener
        status = await sync_to_async(task.status)
        thumbMap = {
            "Download": "https://f004.backblazeb2.com/file/switch-bucket/28dc28f9-0edc-11ef-a65b-d41b81d4a9f0.png",
            "Upload": "https://f004.backblazeb2.com/file/switch-bucket/3cf91693-0edc-11ef-8772-d41b81d4a9f0.png",
            "Seed": "https://f004.backblazeb2.com/file/switch-bucket/32d36a71-0edc-11ef-992c-d41b81d4a9f0.png",
        }
        thumb = thumbMap.get(status) or thumbMap["Seed"]
        taskList.append(
            ListTile(
                (f"[{progress}] " if progress else "") + listener.name[:42] + "...",
                description=f"{status} | {task.processed_bytes()}/{task.size()}",
                thumb=thumb,
                callback_data=f"detail|{task.listener.mid}|{task.gid()}",
                subtitle="",
                progress=ListTileProgress(color="#2F80ED", progress=int(float(progress[:-1]))),
                subtitle_extra=f"Progress: {progress}",
            )
        )

    if taskList:
        comps.append(ListView(options=taskList))
        comps.append(Button("Stop Updating", callback_Data="deleteUpdate"))
    else:
        comps.append(Text("There are no running tasks!"))
    page = AppPage(components=comps, bottom_bar=getBottomBar(page_clb))
    #    print(page.to_json())
    await ctx.event.answer(callback=page)
    if fs:
        await manageUpdatePage(
            ctx, ctx.event.callback_data, start=bool(taskList) or from_app
        )


async def leechDetailPage(ctx: BotContext[CallbackQueryEvent], fs=True):
    userId = ctx.event.action_by_id
    if fs:
        stopTask(userId)

    MID, gID = ctx.event.callback_data.split("|")[1:]
    task: Aria2Status = await getTaskByGid(gid=gID)

    img = Image("https://media.tenor.com/z1-2owqaCVkAAAAj/impatient-kitty.gif")

    comps = [
        Spacer(y=50),
        img,
        Spacer(y=50),
    ]
    results = appTaskHolder.get(int(MID))

    if task:
        listener = task.listener

        progress = (
            await task.progress()
            if iscoroutinefunction(task.progress)
            else task.progress()
        )
        print(173, task, fs)
        status = await sync_to_async(task.status)
        comps.extend(
            [
                Text(f"*{task.name()}*", TextSize.LARGE),
                Spacer(y=10),
                Text(f"*Status:* {status}"),
                Text(f"*Size:* {task.processed_bytes()}/{task.size()}"),
                Text(f"*Speed:* {task.speed()}"),
                Text(f"*ETA:* {task.eta()}"),
            ]
        )
        print(status)
        if status == "Download" and hasattr(task, "leechers_num"):
            comps.append(
                Text(f"*Leechers:* {task.leechers_num()}"),
            )
            try:
                comps.append(Text(f"*Seeders:* {task.seeders_num()}"))
            except Exception as er:
                pass
        comps.append(Text(f"*Progress:* {progress}"))

        if not results and int(listener.userId) == int(userId):
            comps.append(
                Button("Cancel", color="#f5424b", callback_data=f"cancel|{task.gid()}")
            )
    #    print(appTaskHolder, MID)

    if data := results:
        files = data["files"]
        img.url = img.dark_url = (
            "https://media.tenor.com/TvvB4oGK4wMAAAAj/party-dance.gif"
        )

        if len(files) > 1:
            comps.append(Text(f"*{data['name']}*"))
        tiles = []
        for file in files:
            tiles.append(
                ListTile(
                    title=file["name"][:42] + "...",
                    thumb=file.get("thumb")
                    or "https://img.icons8.com/?size=80&id=dankAbX6G5AT&format=png",
                    description=f"Size: {get_readable_file_size(file.get('size'))}",
                    callback_data=f"file|{file.get('id')}",
                )
            )
        if tiles:
            comps.append(Spacer(y=20))
            comps.append(Text("*Result*", TextSize.MEDIUM))
            comps.append(
                ListView(
                    tiles,
                    #                   view_type=ListViewType.LARGE
                )
            )
            print(tiles)
    comps.append(Button("Back to Home", callback_data="Home|self"))
    comps.append(Spacer(y=15))

    await ctx.event.answer(callback=AppPage(components=comps))

    if data := results:
        try:
            del editTask[userId]
        except Exception as er:
            print(er)
        fs = False
    if fs:
        print("managing", 286)
        await manageUpdatePage(ctx, ctx.event.callback_data, start=True)


async def onStartTask(ctx: BotContext[CallbackQueryEvent]):
    """Button callback for  'Start task'"""
    from .mirror_leech import Mirror
    from .ytdlp import YtDlp

    downloader = ctx.event.callback_data == "startDownloadTask"

    user = ctx.event.action_by_id
    userC = appConf.get(user, {})
    torrentLink = userC.get("link")
    if not torrentLink:
        await ctx.event.answer("Please enter link", show_alert=True)
        return

    mode, engine = None, None
    if not downloader:
        mode = userC.get("mode")
        if not mode:
            return await ctx.event.answer("Please select mode!", show_alert=True)
        engine = userC.get("engine")
        if not engine:
            return await ctx.event.answer("Please select engine", show_alert=True)

    async with task_dict_lock:
        msg = randint(80, 888888)
        while msg in task_dict:
            msg = randint(80, 555555)

    if downloader:
        cmd = f"{BotCommands.YtdlCommand[0]} {torrentLink}"
    elif mode == "Mirror":
        cmd = f"{BotCommands.MirrorCommand[0]} {torrentLink}"
    else:
        cmd = f"{BotCommands.LeechCommand[0]} {torrentLink}"

    message = Message(
        app=ctx.app,
        id=msg,
        message=cmd,
        community_id=config_dict.get("APP_COMMUNITY", ctx.event.community_id),
        group_id=config_dict.get("APP_GROUP", ctx.event.group_id),
        user_id=ctx.event.action_by_id,
        user=ctx.event.action_by,
        group_chat=True,
    )
    qbit, isMirror = engine == "Qbit", mode == "Mirror"
    await ctx.event.answer("Starting task!", show_alert=True)
    if downloader:
        YtDlp(
            ctx.app, message, isLeech=True, queryEvent=ctx.event, fromApp=True
        ).newEvent()
    else:
        Leech = not isMirror
        Mirror(ctx.app, message, isQbit=qbit, isLeech=Leech).newEvent()

    ctx.event.callback_data = f"{'Downloader' if downloader else 'Home'}|self"
    await asyncio.sleep(3)
    await onHome(ctx, from_app=True)


async def stopUpdating(ctx: BotContext[CallbackQueryEvent]):
    """button which stops updating"""
    userId = ctx.event.action_by_id
    stopTask(userId)

    await ctx.event.answer("Stopped Updating!", show_alert=True)


async def onEngineInfo(ctx: BotContext[CallbackQueryEvent]):
    """dropdown to set engine"""
    userId = ctx.event.action_by_id
    if not appConf.get(userId):
        appConf[userId] = {}
    appConf[userId]["engine"] = ctx.event.callback_data.split("|")[-1]
    await onHome(ctx)


async def onLinkEnter(ctx: BotContext[CallbackQueryEvent]):
    """Receive link from input box"""
    userId = ctx.event.action_by_id
    if not appConf.get(userId):
        appConf[userId] = {}
    appConf[userId]["link"] = ctx.event.details.input_value


async def onSelectMode(ctx: BotContext[CallbackQueryEvent]):
    """dropdown to select mode"""
    userId = ctx.event.action_by_id
    if not appConf.get(userId):
        appConf[userId] = {}
    appConf[userId]["mode"] = ctx.event.callback_data.split("+")[-1]
    await onHome(ctx)


async def cancelTask(ctx: BotContext[CallbackQueryEvent]):
    """function to cancel torrent task"""
    userId = ctx.event.action_by_id
    gid = ctx.event.callback_data.split("|")[-1]
    print(gid)
    task = await getTaskByGid(gid)
    if not task:
        await ctx.event.answer("Task not found!", show_alert=True)
        return
    task = task.task()
    task.cancel_task()
    print(task, task.task, task.task())


async def onAppCommand(ctx: BotContext[CommandEvent]):
    """Command event on sending /start"""
    m = ctx.event.message
    await m.reply_text(
        "Click below button to open mini-app",
        inline_markup=InlineMarkup(
            [[InlineKeyboardButton("Open APP", callback_data="Home|self")]]
        ),
    )


async def historyPage(ctx: BotContext[CallbackQueryEvent]):
    """History page from bottom bar"""
    comps = []
    userId = ctx.event.action_by_id
    stopTask(userId)

    if DATABASE_URL:
        dbM = await DbManager().get_user_history(user_id=userId)
        for mirror in dbM:
            if not mirror.get("files"):
                continue
            if len(mirror["files"]) > 1:
                comps.append(Text(mirror["name"]))
            if stamp := mirror.get("stamp"):
                date = datetime.fromtimestamp(stamp)
            if tiles := [
                ListTile(
                    file["name"][:42] + "...",
                    description=f"Size: {get_readable_file_size(file.get('size'))}",
                    thumb=file.get("thumb")
                    or "https://img.icons8.com/?size=80&id=dankAbX6G5AT&format=png",
                    callback_data=f"file|{file.get('id')}",
                )
                for file in mirror["files"]
            ]:
                comps.append(
                    ListView(
                        tiles,
                        #                        view_type=ListViewType.LARGE
                    )
                )

        print(dbM)
    else:
        comps.append(Text("History option is disabled by the bot!"))
    page = AppPage(components=comps, bottom_bar=getBottomBar("History"))
    await ctx.event.answer(callback=page)


async def filePage(ctx: BotContext[CallbackQueryEvent]):
    """page which dispay file info"""
    fileId = ctx.event.callback_data.split("|")[-1]
    comps = []
    userId = ctx.event.action_by_id
    stopTask(userId)

    filesHistory = await DbManager().get_user_history(userId)
    findIds = list(
        filter(
            lambda x: any(f["id"] == int(fileId) for f in x.get("files", [])),
            filesHistory,
        )
    )
    try:
        fileInfo = await ctx.app.get_media(fileId)
        name = fileInfo.description.lower()
        if name.endswith((".mp4", ".mkv", ".webm")):
            comps.append(VideoPlayer(url=fileInfo.url, title=name))
        elif name.endswith((".mp3", ".flac")):
            comps.append(
                AudioPlayer(
                    title=name,
                    url=fileInfo.url,
                    thumb=Image(
                        fileInfo.thumbnail_url
                        or "https://static.vecteezy.com/system/resources/thumbnails/010/063/543/small_2x/music-festival-colorful-icon-with-notes-and-the-inscription-music-3d-render-png.png"
                    ),
                )
            )
        else:
            comps.append(Text(f"*{name}*", TextSize.MEDIUM))
        comps.append(Text(f"*File Size:* {get_readable_file_size(fileInfo.file_size)}"))
        if findIds:
            torrentLink = findIds[0]["link"]
            comps.extend((Text("*Link:*"), Text(torrentLink)))
        comps.append(Button("Download Now", url=fileInfo.url))
    except Exception as er:
        print(er)

    await ctx.event.answer(callback=AppPage(components=comps), new_page=True)


async def supportedList(ctx: BotContext[CallbackQueryEvent]):
    comps = [Text("*Supported Sites*", TextSize.SMALL)]
    comps.extend([Text(f"- {text}") for text in sorted(SUPPORTED_SITES)])
    await ctx.event.answer(
        callback=AppPage(
            components=comps, screen=ScreenType.BOTTOM, show_continue=False
        )
    )


bot.add_handler(
    CommandHandler(
        BotCommands.AppCommand,
        onAppCommand,  # filter=CustomFilters.authorized
    )
)

bot.add_handler(
    CallbackQueryHandler(onHome, regexp("Home"))  # & CustomFilters.authorized
)
bot.add_handler(
    CallbackQueryHandler(
        onLinkEnter, regexp("onLinkEnter")  # & CustomFilters.authorized
    )
)
bot.add_handler(
    CallbackQueryHandler(onEngineInfo, regexp("engine"))  # & CustomFilters.authorized
)
bot.add_handler(
    CallbackQueryHandler(onSelectMode, regexp("select"))  # & CustomFilters.authorized
)


bot.add_handler(
    CallbackQueryHandler(
        onStartTask, regexp("startDownloadTask")  # & CustomFilters.authorized
    )
)
bot.add_handler(
    CallbackQueryHandler(onStartTask, regexp("startTask"))  # & CustomFilters.authorized
)

bot.add_handler(
    CallbackQueryHandler(
        leechDetailPage, regexp("detail")  # & CustomFilters.authorized
    )
)
bot.add_handler(
    CallbackQueryHandler(
        stopUpdating, regexp("deleteUpdate")  # & CustomFilters.authorized
    )
)

bot.add_handler(
    CallbackQueryHandler(cancelTask, regexp("cancel"))  # & CustomFilters.authorized
)


bot.add_handler(
    CallbackQueryHandler(onHome, regexp("Downloader"))  # & CustomFilters.authorized
)

bot.add_handler(
    CallbackQueryHandler(historyPage, regexp("History"))  # & CustomFilters.authorized
)

bot.add_handler(
    CallbackQueryHandler(filePage, regexp("file"))  # & CustomFilters.authorized
)
bot.add_handler(
    CallbackQueryHandler(
        supportedList, regexp("viewList")  # & CustomFilters.authorized
    )
)
