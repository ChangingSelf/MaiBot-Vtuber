import asyncio
from .action_sender import action_sender
from .small_actions.talking_head import talking_head
from .small_actions.throw_fish import throw_fish

class ReplyState:
    def __init__(self):
        self.is_thinking = False
        self.is_replying = False
        self.is_viewing = False
        self.is_talking = False
        
    
    async def deal_state(self, state: str):
        if state == "start_thinking":
            self.is_thinking = True
        if state == "finish_thinking":
            self.is_thinking = False
        if state == "start_replying":
            self.is_replying = True
            
        if state == "start_viewing" :
            if not self.is_replying and not self.is_talking:
                await self.send_loading()
            
            asyncio.create_task(throw_fish.throw_fish())
            
    
    async def start_talking(self):
        self.is_talking = True
        await self.send_unloading()
        
        talking_head.is_talking = True
        asyncio.create_task(talking_head.send_random_head_action())
        
    async def stop_talking(self):
        self.is_talking = False
        talking_head.is_talking = False
    
    async def send_loading(self):
        await action_sender.send_action("loading", "......")
        
    async def send_unloading(self):
        await action_sender.send_action("loading", "")
        
        
reply_state = ReplyState()