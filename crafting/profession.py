"""生活技能与制造系统 - 修复版

修复点:
1. 材料检查包含品质要求(低品质材料不能用于高品质配方)
2. 成功率受技能等级 + 配方难度 + 工具品质影响
3. 采集点动态刷新 + 区域分布 + 防蹲点机制
4. 装备属性范围受配方等级和制造者技能影响
5. 制造前原子检查背包空间, 不足则不扣材料
6. 配方有职业/派系限制
7. 工具有耐久, 且影响采集效率和品质
"""
import random
from dataclasses import dataclass, field

# 品质等级: 数值越大品质越高
QUALITY_TIERS = {
    "common": 0,
    "uncommon": 1,
    "rare": 2,
    "epic": 3,
    "legendary": 4,
}

# 职业 -> 可学习的专业
PROFESSION_CLASSES = {
    "blacksmith": {"warrior", "paladin"},
    "alchemy": {"mage", "priest"},
    "leatherworking": {"rogue", "hunter"},
    "enchanting": {"mage", "warlock"},
}


@dataclass
class Recipe:
    rid: str
    name: str
    level: int
    profession: str  # blacksmith/alchemy/...
    materials: dict = field(default_factory=dict)  # item -> (count, min_quality)
    success_rate: float = 1.0
    output: str = ""
    output_quality_range: tuple = (1, 10)
    required_class: str = ""   # 可选: 显式限定职业(空则按专业默认映射)
    required_faction: str = ""  # 可选: 派系限制


@dataclass
class GatheringNode:
    node_id: str
    zone: str = "default"
    x: float = 0.0
    y: float = 0.0
    available: bool = True
    respawn_at: float = 0.0
    last_gatherer: str = ""
    last_gather_time: float = -1e9
    gather_streak: int = 0
    base_interval: float = 60.0


class CraftingSystem:
    def __init__(self, seed: int = 42):
        self.rng = random.Random(seed)
        self.recipes: dict[str, Recipe] = {}
        self.inventory: dict[str, dict] = {}  # player -> {item 或 item@quality: count}
        self.backpack_capacity = 20
        self.tool_durability: dict[str, int] = {}
        self.tool_quality: dict[str, float] = {}  # tool -> 品质系数(1.0 为标准)
        self.learned: dict[str, set] = {}  # player -> {recipe_id}
        self.nodes: dict[str, GatheringNode] = {}
        self.zones: dict[str, tuple] = {"default": (100.0, 100.0)}  # zone -> (width, height)
        self._clock = 0.0  # 内部逻辑时钟, 避免依赖真实时间

    # ---------- 材料与品质 ----------

    @staticmethod
    def _split_item(key: str) -> tuple:
        """背包key支持 'item' 或 'item@quality' 两种形式, 缺省为 common。"""
        base, _, quality = key.partition("@")
        return base, quality or "common"

    def check_materials(self, player: str, recipe: Recipe) -> bool:
        # fix1: 数量与品质双重检查, 只有品质达标的材料才计入
        inv = self.inventory.get(player, {})
        for item, (count, min_quality) in recipe.materials.items():
            min_tier = QUALITY_TIERS.get(min_quality or "common", 0)
            have = sum(
                c for k, c in inv.items()
                if self._split_item(k)[0] == item
                and QUALITY_TIERS.get(self._split_item(k)[1], 0) >= min_tier
            )
            if have < count:
                return False
        return True

    def _consume_materials(self, player: str, recipe: Recipe) -> None:
        # 优先消耗达标的最低品质材料, 保住高品质材料
        inv = self.inventory[player]
        for item, (count, min_quality) in recipe.materials.items():
            min_tier = QUALITY_TIERS.get(min_quality or "common", 0)
            keys = sorted(
                (k for k in inv
                 if self._split_item(k)[0] == item
                 and QUALITY_TIERS.get(self._split_item(k)[1], 0) >= min_tier),
                key=lambda k: QUALITY_TIERS.get(self._split_item(k)[1], 0),
            )
            need = count
            for k in keys:
                if need <= 0:
                    break
                take = min(inv[k], need)
                inv[k] -= take
                need -= take
                if inv[k] <= 0:
                    del inv[k]

    # ---------- 成功率 ----------

    def get_success_rate(self, player_skill: int, recipe: Recipe,
                         tool_quality: float = 1.0) -> float:
        # fix2: 基础成功率 + 技能/难度差修正 + 工具品质修正, 钳制在 [0.05, 0.99]
        skill_bonus = (player_skill - recipe.level) * 0.004
        tool_bonus = (tool_quality - 1.0) * 0.05
        rate = recipe.success_rate + skill_bonus + tool_bonus
        return max(0.05, min(0.99, rate))

    # ---------- 制造 ----------

    def _roll_quality(self, recipe: Recipe, player_skill: int) -> int:
        # fix4: 属性范围受配方等级与制造者技能影响
        lo, hi = recipe.output_quality_range
        level_shift = recipe.level * 0.3
        skill_shift = player_skill * 0.05
        return int(self.rng.randint(lo, hi) + level_shift + skill_shift)

    def craft(self, player: str, recipe_id: str, player_skill: int,
              tool_quality: float = 1.0) -> tuple[bool, str]:
        recipe = self.recipes[recipe_id]
        if not self.check_materials(player, recipe):
            return False, "no materials"
        inv = self.inventory.setdefault(player, {})
        # fix5: 扣材料之前原子检查背包空间, 不足直接失败, 不扣任何材料
        out_key = f"crafted_{recipe.output}"
        if out_key not in inv and len(inv) >= self.backpack_capacity:
            return False, "backpack full"
        self._consume_materials(player, recipe)
        rate = self.get_success_rate(player_skill, recipe, tool_quality)
        if self.rng.random() > rate:
            return False, "failed"
        quality = self._roll_quality(recipe, player_skill)
        inv[out_key] = inv.get(out_key, 0) + 1
        return True, f"crafted_{recipe.output}_q{quality}"

    # ---------- 配方学习(职业/派系限制) ----------

    def can_learn(self, player_class: str, recipe: Recipe,
                  player_faction: str = "") -> bool:
        # fix6: 职业限制(显式指定优先, 否则按专业默认映射) + 派系限制
        if recipe.required_class:
            allowed = {recipe.required_class}
        else:
            allowed = PROFESSION_CLASSES.get(recipe.profession, set())
        if player_class not in allowed:
            return False
        if recipe.required_faction and player_faction != recipe.required_faction:
            return False
        return True

    def learn_recipe(self, player: str, player_class: str, recipe_id: str,
                     player_faction: str = "") -> bool:
        recipe = self.recipes[recipe_id]
        if not self.can_learn(player_class, recipe, player_faction):
            return False
        self.learned.setdefault(player, set()).add(recipe_id)
        return True

    # ---------- 采集: 工具耐久 / 动态刷新 / 区域分布 / 防蹲点 ----------

    def register_tool(self, tool: str, durability: int, quality: float = 1.0) -> None:
        self.tool_durability[tool] = durability
        self.tool_quality[tool] = quality

    def register_zone(self, zone: str, width: float, height: float) -> None:
        self.zones[zone] = (width, height)

    def register_node(self, node_id: str, zone: str = "default",
                      base_interval: float = 60.0) -> GatheringNode:
        node = GatheringNode(node_id=node_id, zone=zone, base_interval=base_interval)
        self._relocate(node)
        self.nodes[node_id] = node
        return node

    def _get_node(self, node_id: str) -> GatheringNode:
        node = self.nodes.get(node_id)
        if node is None:
            node = self.register_node(node_id)
        return node

    def _relocate(self, node: GatheringNode) -> None:
        # 区域分布: 节点在所属区域内随机分布/迁移
        width, height = self.zones.get(node.zone, (100.0, 100.0))
        node.x = self.rng.uniform(0, width)
        node.y = self.rng.uniform(0, height)

    def get_node_respawn(self, zone_population: int) -> float:
        # fix7: 刷新速率随区域人口动态提升(人越多刷得越快), 返回值越大刷新越快
        return 1.0 + max(0, zone_population) / 20.0

    def _respawn_delay(self, node: GatheringNode, zone_population: int) -> float:
        # 动态刷新: 基础间隔 / 人口速率, 再加随机抖动, 无法卡秒蹲点
        rate = self.get_node_respawn(zone_population)
        return node.base_interval / rate * self.rng.uniform(0.7, 1.3)

    def get_nodes_in_zone(self, zone: str) -> list:
        return [n.node_id for n in self.nodes.values() if n.zone == zone]

    def gather(self, node_id: str, tool: str, player: str = "",
               zone_population: int = 1, now: float = None) -> dict:
        # fix6(工具): 耐久为0工具损坏, 无法采集
        durability = self.tool_durability.get(tool, 0)
        if durability <= 0:
            return {"broken": True, "item": None, "count": 0}
        node = self._get_node(node_id)
        if now is None:
            self._clock += 1.0
            now = self._clock
        if not node.available and now < node.respawn_at:
            return {"item": None, "count": 0, "reason": "depleted"}
        if not node.available:
            # 刷新时迁移位置: 蹲点守不到固定坐标
            self._relocate(node)
            node.available = True
        # 防蹲点: 同一玩家短时间内反复采同一节点, 收益递减
        camping = (player and player == node.last_gatherer
                   and now - node.last_gather_time < node.base_interval)
        if camping:
            node.gather_streak += 1
        else:
            node.gather_streak = 0
        penalty = 0.5 ** node.gather_streak
        # fix7(工具): 消耗耐久, 工具品质影响采集效率与产出品质
        self.tool_durability[tool] = durability - 1
        tool_q = self.tool_quality.get(tool, 1.0)
        count = max(1, round(1 * tool_q * penalty))
        quality = max(1, round(2 * tool_q * penalty))
        node.last_gatherer = player
        node.last_gather_time = now
        node.available = False
        node.respawn_at = now + self._respawn_delay(node, zone_population)
        return {"item": "ore", "count": count, "quality": quality}
