from .operator import Operator
import asyncio


class ArknightsSimulator:
    """
    明日方舟模拟器
    """

    def __init__(
        self,
        init_cost: int = 10,
        init_deployable_characters_count: int = 8,
        team: list[Operator] = None,
    ):
        self.current_cost = init_cost
        self.remaining_deployable_characters_count = init_deployable_characters_count
        self.team = team
        self._cost_recovery_task = None
        self._is_running = False

    async def start(self):
        """启动模拟器，开始自动回复费用"""
        if self._is_running:
            return
        self._is_running = True
        self._cost_recovery_task = asyncio.create_task(self._cost_recovery_loop())

    async def stop(self):
        """停止模拟器，停止自动回复费用"""
        if not self._is_running:
            return
        self._is_running = False
        if self._cost_recovery_task:
            self._cost_recovery_task.cancel()
            try:
                await self._cost_recovery_task
            except asyncio.CancelledError:
                pass
            self._cost_recovery_task = None

    async def _cost_recovery_loop(self):
        """自动回复费用的循环"""
        while self._is_running:
            await asyncio.sleep(1)  # 每秒增加1点费用
            self.current_cost += 1
