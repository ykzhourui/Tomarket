import asyncio
from datetime import datetime, timedelta
import json
import os,sys
from random import randint, choices,random
from time import time
from urllib.parse import unquote, quote

import aiohttp
import pytz
from aiohttp_proxy import ProxyConnector
from better_proxy import Proxy
from pyrogram import Client
from pyrogram.errors import Unauthorized, UserDeactivated, AuthKeyUnregistered, FloodWait
from pyrogram.raw.functions.messages import RequestAppWebView
from pyrogram.raw.types import InputBotAppShortName

from typing import Callable
import functools
from tzlocal import get_localzone
from bot.config import settings
from bot.exceptions import InvalidSession
from bot.utils import logger
from .agents import generate_random_user_agent
from .headers import headers
from .api_check import check_base_url

def error_handler(func: Callable):
    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except Exception as e:
            await asyncio.sleep(1)
    return wrapper

def convert_to_local_and_unix(iso_time):
    dt = datetime.fromisoformat(iso_time.replace('Z', '+00:00'))
    local_dt = dt.astimezone(get_localzone())
    unix_time = int(local_dt.timestamp())
    return unix_time

def next_daily_check():
    current_time = datetime.now()
    next_day = current_time + timedelta(days=1)
    return next_day

class Tapper:
    def __init__(self, tg_client: Client, proxy: str | None):
        self.session_name = tg_client.name
        self.tg_client = tg_client
        self.proxy = proxy

    async def get_tg_web_data(self) -> str:
        
        if self.proxy:
            proxy = Proxy.from_str(self.proxy)
            proxy_dict = dict(
                scheme=proxy.protocol,
                hostname=proxy.host,
                port=proxy.port,
                username=proxy.login,
                password=proxy.password
            )
        else:
            proxy_dict = None

        self.tg_client.proxy = proxy_dict

        try:
            if not self.tg_client.is_connected:
                try:
                    await self.tg_client.connect()

                except (Unauthorized, UserDeactivated, AuthKeyUnregistered):
                    raise InvalidSession(self.session_name)
            
            while True:
                try:
                    peer = await self.tg_client.resolve_peer('Tomarket_ai_bot')
                    break
                except FloodWait as fl:
                    fls = fl.value

                    logger.warning(f"{self.session_name} | FloodWait {fl}")
                    logger.info(f"{self.session_name} | Sleep {fls}s")
                    await asyncio.sleep(fls + 10)
            
            ref_id = choices([settings.REF_ID, "0001b3Lf"], weights=[70, 30], k=1)[0] # change this to weights=[100, 0] if you don't want to support me
            web_view = await self.tg_client.invoke(RequestAppWebView(
                peer=peer,
                app=InputBotAppShortName(bot_id=peer, short_name="app"),
                platform='android',
                write_allowed=True,
                start_param=ref_id
            ))

            auth_url = web_view.url
            tg_web_data = unquote(
                string=unquote(string=auth_url.split('tgWebAppData=')[1].split('&tgWebAppVersion')[0]))
            tg_web_data_parts = tg_web_data.split('&')

            user_data = quote(tg_web_data_parts[0].split('=')[1])
            chat_instance = tg_web_data_parts[1].split('=')[1]
            chat_type = tg_web_data_parts[2].split('=')[1]
            auth_date = tg_web_data_parts[4].split('=')[1]
            hash_value = tg_web_data_parts[5].split('=')[1]

            init_data = (f"user={user_data}&chat_instance={chat_instance}&chat_type={chat_type}&start_param={ref_id}&auth_date={auth_date}&hash={hash_value}")
            
            if self.tg_client.is_connected:
                await self.tg_client.disconnect()

            return ref_id, init_data

        except Exception as error:
            logger.error(f"{self.session_name} | Unknown error: {error}")
            await asyncio.sleep(delay=3)
            return None, None

    @error_handler
    async def make_request(self, http_client, method, endpoint=None, url=None, **kwargs):
        full_url = url or f"https://api-web.tomarket.ai/tomarket-game/v1{endpoint or ''}"
        response = await http_client.request(method, full_url, **kwargs)
        return await response.json()
        
    @error_handler
    async def login(self, http_client, tg_web_data: str, ref_id: str) -> tuple[str, str]:
        response = await self.make_request(http_client, "POST", "/user/login", json={"init_data": tg_web_data, "invite_code": ref_id, "from":"","is_bot":False})
        return response.get('data', {}).get('access_token', None)

    @error_handler
    async def check_proxy(self, http_client: aiohttp.ClientSession) -> None:
        response = await self.make_request(http_client, 'GET', url='https://httpbin.org/ip', timeout=aiohttp.ClientTimeout(5))
        ip = response.get('origin')
        logger.info(f"{self.session_name} | Proxy IP: {ip}")

    @error_handler
    async def get_balance(self, http_client):
        return await self.make_request(http_client, "POST", "/user/balance")

    @error_handler
    async def claim_daily(self, http_client):
        return await self.make_request(http_client, "POST", "/daily/claim", json={"game_id": "fa873d13-d831-4d6f-8aee-9cff7a1d0db1"})

    @error_handler
    async def start_farming(self, http_client):
        return await self.make_request(http_client, "POST", "/farm/start", json={"game_id": "53b22103-c7ff-413d-bc63-20f6fb806a07"})

    @error_handler
    async def claim_farming(self, http_client):
        return await self.make_request(http_client, "POST", "/farm/claim", json={"game_id": "53b22103-c7ff-413d-bc63-20f6fb806a07"})

    @error_handler
    async def play_game(self, http_client):
        return await self.make_request(http_client, "POST", "/game/play", json={"game_id": "59bcd12e-04e2-404c-a172-311a0084587d"})

    @error_handler
    async def claim_game(self, http_client, points=None):
        return await self.make_request(http_client, "POST", "/game/claim", json={"game_id": "59bcd12e-04e2-404c-a172-311a0084587d", "points": points})


    @error_handler
    async def get_tasks(self, http_client,data=None):
        return await self.make_request(http_client, "POST", "/tasks/list", json=data)

    @error_handler
    async def start_task(self, http_client, data):
        return await self.make_request(http_client, "POST", "/tasks/start", json=data)

    @error_handler
    async def check_task(self, http_client, data):
        return await self.make_request(http_client, "POST", "/tasks/check", json=data)

    @error_handler
    async def claim_task(self, http_client, data):
        return await self.make_request(http_client, "POST", "/tasks/claim", json=data)
    @error_handler
    async def get_ticket(self, http_client, data):
        return await self.make_request(http_client, "POST", "/user/tickets", json=data)
    
    @error_handler
    async def play_ticket(self, http_client):
        return await self.make_request(http_client, "POST", "/spin/raffle", json={"category":"ticket_spin_1"})

    @error_handler
    async def get_combo(self, http_client,data=None):
        return await self.make_request(http_client, "POST", "/tasks/puzzle",json=data)
    
    @error_handler
    async def claim_combo(self, http_client,data):
        return await self.make_request(http_client, "POST", "/tasks/puzzleClaim",json=data)

    @error_handler
    async def get_stars(self, http_client):
        return await self.make_request(http_client, "POST", "/tasks/classmateTask")

    @error_handler
    async def start_stars_claim(self, http_client, data):
        return await self.make_request(http_client, "POST", "/tasks/classmateStars", json=data)
    
    @error_handler
    async def check_blacklist(self, http_client, data):
        return await self.make_request(http_client, "POST", "/rank/blacklist", json=data)
    
    @error_handler
    async def get_puzzle(self, taskId):
        urls = [
            "https://raw.githubusercontent.com/yanpaing007/Tomarket/refs/heads/main/bot/config/combo.json",
            "https://raw.githubusercontent.com/zuydd/database/refs/heads/main/tomarket.json"
        ]
        
        async with aiohttp.ClientSession() as session:
            for idx, url in enumerate(urls):
                repo_type = "main" if idx == 0 else "backup"
                try:
                    async with session.get(url) as response:
                        if response.status == 200:
                            try:
                                text = await response.text()
                                data = json.loads(text)
                                puzzle = data.get('puzzle', None)
                                code = puzzle.get('code') if puzzle else data.get('code', None)
                                
                                if puzzle and puzzle.get('task_id') == taskId:
                                    logger.info(f"{self.session_name} - Puzzle retrieved successfully from {repo_type} repo: {puzzle}")
                                    return code
                                elif repo_type == "backup":
                                    logger.info(f"{self.session_name} - Puzzle not found even in backup repo,trying from local combo.json...")
                                    get_local = self.get_local_puzzle(taskId)
                                    if get_local:
                                        return get_local
                                    return None
                            except json.JSONDecodeError as json_err:
                                logger.error(f"{self.session_name} - Error parsing JSON from {repo_type} repo: {json_err}")
                        else:
                            logger.error(f"{self.session_name} - Failed to retrieve puzzle from {repo_type} repo. Status code: {response.status}")
                except aiohttp.ClientError as e:
                    logger.error(f"{self.session_name} - Exception occurred while retrieving puzzle from {repo_type} repo: {e}")
        
        logger.info(f"{self.session_name} - Failed to retrieve puzzle from both main and backup repos.")
        return None
    
    def get_local_puzzle(self,taskId):
        try:
            with open('bot/config/combo.json', 'r') as local_file:
                data = json.load(local_file)
                puzzle = data.get('puzzle', None)
                code = puzzle.get('code') if puzzle else None

                if puzzle and puzzle.get('task_id') == taskId:
                    logger.info(f"{self.session_name} - Puzzle retrieved successfully from local file: {puzzle}")
                    return code
                else:
                    logger.info(f"{self.session_name} - Puzzle with {taskId} not found in local file.Please change the task_id and code in combo.json if you knew the code.")
                    return None

        except FileNotFoundError:
            logger.error(f"{self.session_name} - Local file combo.json not found.")
        except json.JSONDecodeError as json_err:
            logger.error(f"{self.session_name} - Error parsing JSON from local file: {json_err}")

        logger.info(f"{self.session_name} - Failed to retrieve puzzle from both main and backup repos, and local file.")
        return None
    
    

    @error_handler
    async def create_rank(self, http_client):
        evaluate = await self.make_request(http_client, "POST", "/rank/evaluate")
        if evaluate and evaluate.get('status', 404) == 0:
            await self.make_request(http_client, "POST", "/rank/create")
            return True
        return False
    
    @error_handler
    async def get_rank_data(self, http_client):
        return await self.make_request(http_client, "POST", "/rank/data")

    @error_handler
    async def upgrade_rank(self, http_client, stars: int):
        return await self.make_request(http_client, "POST", "/rank/upgrade", json={'stars': stars})
    
    @error_handler
    async def name_change(self, emoji: str) -> bool:
        # await asyncio.sleep(random.randint(3, 5))
        if self.proxy:
            proxy = Proxy.from_str(self.proxy)
            proxy_dict = dict(
                scheme=proxy.protocol,
                hostname=proxy.host,
                port=proxy.port,
                username=proxy.login,
                password=proxy.password
            )
        else:
            proxy_dict = None

        self.tg_client.proxy = proxy_dict

        if not self.tg_client.is_connected:
                try:
                    logger.info(f"{self.session_name} | Sleeping 5 seconds before connecting tg_client...")
                    await asyncio.sleep(5)
                    await self.tg_client.connect()

                except (Unauthorized, UserDeactivated, AuthKeyUnregistered):
                    raise InvalidSession(self.session_name)

        try:
            user = await self.tg_client.get_me()
            
            current_name = user.first_name
            logger.info(f"{self.session_name} | Current Name: <y>{current_name}</y>")
            
            new_name = current_name + emoji if emoji not in current_name else current_name
            
            if current_name != new_name:
                try:
                    await self.tg_client.update_profile(first_name=new_name)
                    logger.info(f"{self.session_name} | Name changed to: <y>{new_name}</y>")
                    return True  
                except Exception as e:
                    logger.error(f"{self.session_name} | Error updating {new_name}: {str(e)}")
                    await asyncio.sleep(5)
                    return False
            else:
                logger.info(f"{self.session_name} | Name already contains the emoji.")
                return False

        except Exception as e:
            logger.error(f"{self.session_name} | Error during name change: {str(e)}")
            return False

        finally:
            if self.tg_client.is_connected:
                await asyncio.sleep(5)
                await self.tg_client.disconnect()
            await asyncio.sleep(randint(10, 20))
    
    async def run(self) -> None:        
        if settings.USE_RANDOM_DELAY_IN_RUN:
            random_delay = randint(settings.RANDOM_DELAY_IN_RUN[0], settings.RANDOM_DELAY_IN_RUN[1])
            logger.info(f"{self.tg_client.name} | Bot will start in <light-red>{random_delay}s</light-red>")
            await asyncio.sleep(delay=random_delay)
       
            
        proxy_conn = ProxyConnector().from_url(self.proxy) if self.proxy else None
        http_client = aiohttp.ClientSession(headers=headers, connector=proxy_conn)
        if self.proxy:
            await self.check_proxy(http_client=http_client)
        
        if settings.FAKE_USERAGENT:            
            http_client.headers['User-Agent'] = generate_random_user_agent(device_type='android', browser_type='chrome')


        end_farming_dt = 0
        token_expiration = 0
        tickets = 0
        next_combo_check = 0
        next_check_time = None
        
        while True:
            try:
                if check_base_url() is False:
                        sys.exit(
                            "Detected api change! Stopped the bot for safety. Please raise an issue on the GitHub repository.")
                if http_client.closed:
                    if proxy_conn:
                        if not proxy_conn.closed:
                            proxy_conn.close()

                    proxy_conn = ProxyConnector().from_url(self.proxy) if self.proxy else None
                    http_client = aiohttp.ClientSession(headers=headers, connector=proxy_conn)
                    if settings.FAKE_USERAGENT:            
                        http_client.headers['User-Agent'] = generate_random_user_agent(device_type='android', browser_type='chrome')
                current_time = time()
                if current_time >= token_expiration:
                    if (token_expiration != 0):
                        logger.info(f"{self.session_name} | <yellow>Token expired, refreshing...</yellow>")
                    ref_id, init_data = await self.get_tg_web_data()
                    access_token = await self.login(http_client=http_client, tg_web_data=init_data, ref_id=ref_id)
                    
                if not access_token:
                    logger.error(f"{self.session_name} | <light-red>Failed login</light-red>")
                    logger.info(f"{self.session_name} | Sleep <light-red>300s</light-red>")
                    await asyncio.sleep(delay=300)
                    continue
                else:
                    logger.info(f"{self.session_name} | <green>🍅 Login successful</green>")
                    http_client.headers["Authorization"] = f"{access_token}"
                    token_expiration = time() + 3600
                await asyncio.sleep(delay=1)
                
                balance = await self.get_balance(http_client=http_client)
                if 'data' not in balance:
                    if balance.get('status') == 401:
                        logger.info(f"{self.session_name} | Access Denied. Re-authenticating...")
                        ref_id, init_data = await self.get_tg_web_data()
                        access_token = await self.login(http_client=http_client, tg_web_data=init_data, ref_id=ref_id)
                        if not access_token:
                            logger.error(f"{self.session_name} | <light-red>Failed login</light-red>")
                            logger.info(f"{self.session_name} | Sleep <light-red>300s</light-red>")
                            await asyncio.sleep(300)
                            continue
                        else:
                            logger.info(f"{self.session_name} | <green>🍅 Login successful</green>")
                            http_client.headers["Authorization"] = f"{access_token}"
                            token_expiration = time() + 3600
                            balance = await self.get_balance(http_client=http_client)
                    else:
                        logger.error(f"{self.session_name} | Balance response missing 'data' key: {balance}")
                        continue

                available_balance = balance['data'].get('available_balance', 0)
                logger.info(f"{self.session_name} | Current balance | <light-red>{available_balance} 🍅</light-red>")
                ramdom_end_time = randint(350, 500)
                if 'farming' in balance['data']:
                    end_farm_time = balance['data']['farming']['end_at']
                    if end_farm_time > time():
                        end_farming_dt = end_farm_time + ramdom_end_time
                        logger.info(f"{self.session_name} | Farming in progress, next claim in <light-red>{round((end_farming_dt - time()) / 60)}m.</light-red>")

                if time() > end_farming_dt:
                    claim_farming = await self.claim_farming(http_client=http_client)
                    if claim_farming and 'status' in claim_farming:
                        if claim_farming.get('status') == 500:
                            start_farming = await self.start_farming(http_client=http_client)
                            if start_farming and 'status' in start_farming and start_farming['status'] in [0, 200]:
                                logger.success(f"{self.session_name} | Farm started.. 🍅")
                                end_farming_dt = start_farming['data']['end_at'] + ramdom_end_time
                                logger.info(f"{self.session_name} | Next farming claim in <light-red>{round((end_farming_dt - time()) / 60)}m.</light-red>")
                        elif claim_farming.get('status') == 0:
                            farm_points = claim_farming['data']['claim_this_time']
                            logger.success(f"{self.session_name} | Success claim farm. Reward: <light-red>+{farm_points}</light-red> 🍅")
                            start_farming = await self.start_farming(http_client=http_client)
                            if start_farming and 'status' in start_farming and start_farming['status'] in [0, 200]:
                                logger.success(f"{self.session_name} | Farm started.. 🍅")
                                end_farming_dt = start_farming['data']['end_at'] + ramdom_end_time
                                logger.info(f"{self.session_name} | Next farming claim in <light-red>{round((end_farming_dt - time()) / 60)}m.</light-red>")
                    await asyncio.sleep(1.5)


                if settings.AUTO_DAILY_REWARD and (next_check_time is None or datetime.now() > next_check_time):
                    claim_daily = await self.claim_daily(http_client=http_client)
                    if claim_daily and 'status' in claim_daily and claim_daily.get("status", 400) != 400:
                        logger.success(f"{self.session_name} | Daily: <light-red>{claim_daily['data']['today_game']}</light-red> reward: <light-red>{claim_daily['data']['today_points']}</light-red>")
                    next_check_time = next_daily_check()
                    logger.info(f"{self.session_name} | Next daily check in <light-red>{next_check_time}</light-red>")

                await asyncio.sleep(1.5)

                if settings.AUTO_PLAY_GAME:
                    ticket = await self.get_balance(http_client=http_client)
                    tickets = ticket.get('data', {}).get('play_passes', 0)
                    logger.info(f"{self.session_name} | Game Play Tickets: {tickets} 🎟️")

                    await asyncio.sleep(1.5)
                    if tickets > 0:
                        logger.info(f"{self.session_name} | Start ticket games...")
                        games_points = 0
                        retry_count = 0
                        max_retries = 5
                        if settings.PLAY_RANDOM_GAME:
                            if  tickets > settings.PLAY_RANDOM_GAME_COUNT[1]: 
                                tickets = randint(settings.PLAY_RANDOM_GAME_COUNT[0], settings.PLAY_RANDOM_GAME_COUNT[1])
                                logger.info(f"{self.session_name} | Playing with: {tickets} 🎟️ this round")
                            

                        while tickets > 0:
                            logger.info(f"{self.session_name} | Tickets remaining: {tickets} 🎟️")
                            try:
                                play_game = await self.play_game(http_client=http_client)
                                if play_game and 'status' in play_game:
                                    if play_game.get('status') == 0:
                                        await asyncio.sleep(30)  
                                        
                                        claim_game = await self.claim_game(http_client=http_client, points=randint(settings.POINTS_COUNT[0], settings.POINTS_COUNT[1]))
                                        if claim_game and 'status' in claim_game:
                                            if claim_game['status'] == 500 and claim_game['message'] == 'game not start':
                                                retry_count += 1
                                                if retry_count >= max_retries:
                                                    logger.warning(f"{self.session_name} | Max retries reached, stopping game attempts.")
                                                    break
                                                logger.info(f"{self.session_name} | Game not started, retrying...")
                                                continue

                                            if claim_game.get('status') == 0:
                                                tickets -= 1
                                                games_points += claim_game.get('data', {}).get('points', 0)
                                                logger.success(f"{self.session_name} | Claimed points: <light-red>+{claim_game.get('data', {}).get('points', 0)} </light-red>🍅")
                                                await asyncio.sleep(randint(3, 5))

                            except Exception as e:
                                logger.error(f"{self.session_name} | An error occurred: {e}")
                                await asyncio.sleep(5)

                        logger.info(f"{self.session_name} | Games finished! Claimed points: <light-red>{games_points} 🍅</light-red>")

                if settings.AUTO_TASK:
                    logger.info(f"{self.session_name} | Start checking tasks.")
                    tasks = await self.get_tasks(http_client=http_client, data={"language_code":"en", "init_data":init_data})
                    tasks_list = []

                    if tasks and tasks.get("status", 500) == 0:
                        for category, task_group in tasks["data"].items():
                            if isinstance(task_group, list):
                                for task in task_group:
                                    if isinstance(task, dict):  
                                        if task.get('enable') and not task.get('invisible', False) and task.get('status') != 3:
                                            if task.get('startTime') and task.get('endTime'):
                                                task_start = convert_to_local_and_unix(task['startTime'])
                                                task_end = convert_to_local_and_unix(task['endTime'])
                                        
                                                if task_start <= time() <= task_end  and task.get('type') not in ['charge_stars_season2', 'chain_donate_free','daily_donate','new_package','charge_stars_season3']:
                                                    tasks_list.append(task)
                                            
                                            elif task.get('type') not in ['wallet', 'mysterious', 'classmate', 'classmateInvite', 'classmateInviteBack', 'charge_stars_season2','chain_donate_free','daily_donate','charge_stars_season3']:
                                                tasks_list.append(task)
                                        if task.get('type') == 'youtube' and task.get('status') != 3:
                                            tasks_list.append(task)
                            elif isinstance(task_group, dict):  
                                for group_name, group_tasks in task_group.items():
                                    if isinstance(group_tasks, list):
                                        for task in group_tasks:
                                            if task.get('enable') or not task.get('invisible', False):
                    
                                                tasks_list.append(task)
                    if len(tasks_list) == 0:
                        logger.info(f"{self.session_name} | No tasks available.")
                    else:
                        logger.info(f"{self.session_name} | Tasks collected: {len(tasks_list)}")
                    for task in tasks_list:
                        wait_second = task.get('waitSecond', 0)
                        claim = None
                        check = None
                        
                        if task.get('type') == 'emoji' and settings.AUTO_TASK: # Emoji task
                                logger.info(f"{self.session_name} | Start task <light-red>{task['name']}.</light-red> Wait {30}s 🍅")
                                await asyncio.sleep(30)
                                await self.name_change(emoji='🍅')
        
                                starttask = await self.start_task(http_client=http_client, data={'task_id': task['taskId'],'init_data':init_data})
                                await asyncio.sleep(3)
                                check = await self.check_task(http_client=http_client, data={'task_id': task['taskId'], 'init_data': init_data})
                                await asyncio.sleep(3)
                                if check:
                                    logger.info(f"{self.session_name} | Task <light-red>{task['name']}</light-red> checked! 🍅")
                                    claim = await self.claim_task(http_client=http_client, data={'task_id': task['taskId']})
                        else:
                            starttask = await self.start_task(http_client=http_client, data={'task_id': task['taskId'],'init_data':init_data})
                            task_data = starttask.get('data', {}) if starttask else None
                            if task_data == 'ok' or task_data.get('status') == 1 or task_data.get('status') ==2 if task_data else False:
                                logger.info(f"{self.session_name} | Start task <light-red>{task['name']}.</light-red> Wait {wait_second}s 🍅")
                                await asyncio.sleep(wait_second + 3)
                                await self.check_task(http_client=http_client, data={'task_id': task['taskId'],'init_data':init_data})
                                await asyncio.sleep(3)
                                claim = await self.claim_task(http_client=http_client, data={'task_id': task['taskId']})
                        if claim:
                                if claim['status'] == 0:
                                    reward = task.get('score', 'unknown')
                                    logger.success(f"{self.session_name} | Task <light-red>{task['name']}</light-red> claimed! Reward: {reward} 🍅")
                                else:
                                    logger.info(f"{self.session_name} | Task <light-red>{task['name']}</light-red> not claimed. Reason: {claim.get('message', 'Unknown error')}")
                        await asyncio.sleep(2)

                await asyncio.sleep(3)

                if await self.create_rank(http_client=http_client):
                    logger.success(f"{self.session_name} | Rank created! 🍅")
                
                if settings.AUTO_RANK_UPGRADE:
                    rank_data = await self.get_rank_data(http_client=http_client)
                    unused_stars = rank_data.get('data', {}).get('unusedStars', 0)
                    current_rank = rank_data.get('data', {}).get('currentRank', "Unknown rank").get('name', "Unknown rank")
                    
                    try:
                        unused_stars = int(float(unused_stars)) 
                    except ValueError:
                        unused_stars = 0
                    logger.info(f"{self.session_name} | Unused stars {unused_stars} ⭐")
                    if unused_stars > 0:
                        upgrade_rank = await self.upgrade_rank(http_client=http_client, stars=unused_stars)
                        if upgrade_rank.get('status', 500) == 0:
                            logger.success(f"{self.session_name} | Rank upgraded! 🍅")
                        else:
                            logger.info(
                                f"{self.session_name} | Rank not upgraded. Reason: <light-red>{upgrade_rank.get('message', 'Unknown error')}</light-red>")
                    if current_rank:
                        logger.info(f"{self.session_name} | Current rank: <cyan>{current_rank}</cyan>")
                            
                            
                            
                if settings.AUTO_CLAIM_COMBO and next_combo_check < time():
                    combo_info = await self.get_combo(http_client, data={"language_code": "en", "init_data": init_data})

                    if combo_info is None or not isinstance(combo_info, dict):
                        logger.error(f"{self.session_name} | Failed to retrieve combo info | Response: {combo_info}")
                        return
                    
                    combo_info_data = combo_info.get('data', [None])[0]
                    if not combo_info_data:
                        logger.error(f"{self.session_name} | Combo info data is missing or invalid!")
                        return

                    start_time = combo_info_data.get('startTime')
                    end_time = combo_info_data.get('endTime')
                    status = combo_info_data.get('status')
                    task_id = combo_info_data.get('taskId')
                    task_type = combo_info_data.get('type')

                    if combo_info.get('status') == 0 and combo_info_data is not None:
                        if status > 0:
                            logger.info(f"{self.session_name} | Daily Combo already claimed.")
                            try:
                                next_combo_check = int(datetime.fromisoformat(end_time).timestamp())
                                logger.info(f"{self.session_name} | Next combo check in <light-red>{round((next_combo_check - time()) / 60)}m.</light-red>")
                            except ValueError as ve:
                                logger.error(f"{self.session_name} | Error parsing combo end time: {end_time} | Exception: {ve}")

                        try:
                            combo_end_time = datetime.fromisoformat(end_time)
                            if status == 0 and combo_end_time > datetime.now():
                                star_amount = combo_info_data.get('star')
                                games_token = combo_info_data.get('games')
                                tomato_token = combo_info_data.get('score')

                                
                                payload =await self.get_puzzle(task_id)
                                if payload is None:
                                    logger.warning(f"{self.session_name} | Failed to retrieve puzzle payload,puzzle might expire! Raise an issue on the GitHub repository.")
                                else:

                                    combo_json = {"task_id": task_id, "code": payload}
                
                                    claim_combo = await self.claim_combo(http_client, data=combo_json)
                                    if (claim_combo is not None and 
                                        claim_combo.get('status') == 0 and 
                                        claim_combo.get('message') == '' and 
                                        isinstance(claim_combo.get('data'), dict) and 
                                        not claim_combo['data']):
                                        
                                        logger.success(
                                            f"{self.session_name} | Claimed combo | Stars: +{star_amount} ⭐ | Games Token: +{games_token} 🎟️ | Tomatoes: +{tomato_token} 🍅"
                                        )

                                        next_combo_check = int(combo_end_time.timestamp())
                                        logger.info(f"{self.session_name} | Next combo check in <light-red>{round((next_combo_check - time()) / 60)}m.</light-red>")
                                    else:
                                        logger.info(f"{self.session_name} | Combo not claimed. Reason: <light-red>{claim_combo.get('message', 'Unknown error')}</light-red>")

                        except ValueError as ve:
                            logger.error(f"{self.session_name} | Error parsing combo end time: {end_time} | Exception: {ve}")
                        except Exception as e:
                            logger.error(f"{self.session_name} | An error occurred while processing the combo: {e}")

                    await asyncio.sleep(1.5)
                    
                    
                            
                if settings.AUTO_RAFFLE:
                    tickets = await self.get_ticket(http_client=http_client, data={"language_code":"en","init_data":init_data})
                    if tickets and tickets.get('status', 500) == 0:
                        tickets = tickets.get('data', {}).get('ticket_spin_1', 0)
                        
                        if tickets > 0:
                            logger.info(f"{self.session_name} | Raffle Tickets: <light-red>{tickets} 🎟️</light-red>")
                            logger.info(f"{self.session_name} | Start ticket raffle...")
                            while tickets > 0:
                                play_ticket = await self.play_ticket(http_client=http_client)
                                if play_ticket and play_ticket.get('status', 500) == 0:
                                    results = play_ticket.get('data', {}).get('results', [])
                                    if results:
                                        raffle_result = results[0]  # Access the first item in the list
                                        amount = raffle_result.get('amount', 0)
                                        item_type = raffle_result.get('type', 0)
                                        logger.success(f"{self.session_name} | Raffle result: {amount} | <light-red>{item_type}</light-red>")
                                    tickets -= 1
                                    await asyncio.sleep(5)
                            logger.info(f"{self.session_name} | Raffle finish! 🍅")
                        else:
                            logger.info(f"{self.session_name} | No raffle tickets available!")
                            
                if settings.AUTO_ADD_WALLET:
                    wallet_file_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'wallet.json')

                    with open(wallet_file_path, 'r') as wallet_file:
                        wallet_data = json.load(wallet_file)
                        my_address = wallet_data.get(self.session_name, {}).get('address', None)
                        if not my_address:
                            logger.warning(f"{self.session_name} | Wallet address not found for {self.session_name} in wallet.json")
                        else:

                            tomarket_wallet = await self.make_request(http_client, "POST", "/tasks/walletTask")
                            if tomarket_wallet and tomarket_wallet.get('status', 500) == 0:
                                server_address = tomarket_wallet.get('data', {}).get('walletAddress', None)
                                if server_address == my_address:
                                    logger.info(f"{self.session_name} | Current wallet address: '{server_address}'!")
                                if server_address == '':
                                    logger.info(f"{self.session_name} | Wallet address '{my_address}' not found in tomarket bot! Trying to add...")
                                    
                                    add_wallet = await self.make_request(http_client, "POST", "/tasks/address", json={"wallet_address": my_address})
                                    if add_wallet and add_wallet.get('status', 500) == 0:
                                        logger.success(f"{self.session_name} | Wallet address '{my_address}' added successfully!")
                                    else:
                                        logger.error(f"{self.session_name} | Failed to add wallet address.Reason: {add_wallet.get('message', 'Unknown error')}")
                                elif server_address != my_address:
                                    logger.info(f"{self.session_name} | Wallet address mismatch! Server: '{server_address}' | Your Address: '{my_address}'")
                                    logger.info(f"{self.session_name} | Trying to remove wallet address...")
                                    remove_wallet = await self.make_request(http_client, "POST", "/tasks/deleteAddress")
                                    if remove_wallet and remove_wallet.get('status', 500) == 0 and remove_wallet.get('data',{}) == 'ok':
                                        logger.success(f"{self.session_name} | Wallet address removed successfully!")
                                        logger.info(f"{self.session_name} | Trying to add wallet address...")
                                        add_wallet = await self.make_request(http_client, "POST", "/tasks/address", json={"wallet_address": my_address})
                                        if add_wallet and add_wallet.get('status', 500) == 0:
                                            logger.success(f"{self.session_name} | Wallet address '{my_address}' added successfully!")
                                        else:
                                            logger.error(f"{self.session_name} | Failed to add wallet address.Reason: {add_wallet.get('message', 'Unknown error')}")
                                    else:
                                        logger.error(f"{self.session_name} | Failed to remove wallet address!") 
                            else:
                                logger.error(f"{self.session_name} | Failed to retrieve wallet information from tomarket bot! Status: {tomarket_wallet.get('status', 'Unknown')}")
                
                tomarket_wallet = await self.make_request(http_client, "POST", "/tasks/walletTask")
                if tomarket_wallet and tomarket_wallet.get('status', 500) == 0:
                    current_address = tomarket_wallet.get('data', {}).get('walletAddress', None)
                    if current_address == '' or current_address is None:
                        logger.info(f"{self.session_name} | Wallet address not found in tomarket bot, add it before OCT 31!")
                    else:
                        logger.info(f"{self.session_name} | Current wallet address: <cyan>'{current_address}'</cyan>")
                        

                sleep_time = end_farming_dt - time()
                logger.info(f'{self.session_name} | Sleep <light-red>{round(sleep_time / 60, 2)}m.</light-red>')
                await asyncio.sleep(sleep_time)
                await http_client.close()
                if proxy_conn:
                    if not proxy_conn.closed:
                        proxy_conn.close()
            except InvalidSession as error:
                raise error

            except Exception as error:
                logger.error(f"{self.session_name} | Unknown error: {error}")
                await asyncio.sleep(delay=3)
                logger.info(f'{self.session_name} | Sleep <light-red>10m.</light-red>')
                await asyncio.sleep(600)
                


async def run_tapper(tg_client: Client, proxy: str | None):
    try:
        await Tapper(tg_client=tg_client, proxy=proxy).run()
    except InvalidSession:
        logger.error(f"{tg_client.name} | Invalid Session")
