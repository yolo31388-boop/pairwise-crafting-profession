"""生活技能与制造系统"""
import random
from dataclasses import dataclass, field

QUALITY_ORDER = ("common", "uncommon", "rare", "epic", "legendary")

# 各生活技能允许学习的职业
PROFESSION_CLASSES = {
    "blacksmith": {"warrior", "paladin", "death_knight"},
    "alchemy": {"mage", "priest", "warlock", "druid"},
    "leatherworking": {"hunter", "rogue", "druid"},
    "engineering": {"hunter", "rogue", "warrior"},
    "enchanting": {"mage", "priest", "warlock"},
    "cooking": {"warrior", "paladin", "mage", "priest", "hunter",
                "rogue", "warlock", "druid", "death_knight"},
}

# 工具定义：耐久上限 / 采集效率 / 产出品质加成
TOOL_DEFS = {
    "pickaxe": {"durability": 100, "efficiency": 1.2, "quality_bonus": 0},
    "axe": {"durability": 100, "efficiency": 1.1, "quality_bonus": 0},
    "sickle": {"durability": 80, "efficiency": 1.0, "quality_bonus": 0},
    "crafting_kit": {"durability": 50, "efficiency": 1.0, "quality_bonus": 0},
}

# 工具品质对制造成功率的加成
TOOL_QUALITY_BONUS = {
    "common": 0.0, "uncommon": 0.02, "rare": 0.05, "epic": 0.08, "legendary": 0.12,
}

@dataclass
class Recipe:
    rid: str
    name: str
    level: int
    profession: str  # blacksmith/alchemy
    materials: dict = field(default_factory=dict)  # item -> (count, min_quality)
    success_rate: float = 1.0
    output: str = ""
    output_quality_range: tuple = (1, 10)
    faction: str = ""           # 派系限制，空为不限
    allowed_classes: tuple = ()  # 职业限制，空则按专业默认表

class CraftingSystem:
    def __init__(self, seed: int = 42):
        self.rng = random.Random(seed)
        self.recipes: dict[str, Recipe] = {}
        self.inventory: dict[str, dict] = {}  # player -> {item: count 或 {quality: count}}
        self.backpack_capacity = 20
        self.tool_durability: dict[str, int] = {}
        self.tool_quality: dict[str, str] = {}  # tool -> quality
        # 区域分布：不同区域的刷新修正系数
        self.zone_modifiers: dict[str, float] = {"default": 1.0}

    @staticmethod
    def _qindex(quality: str) -> int:
        return QUALITY_ORDER.index(quality)

    def _qualifying_count(self, entry, min_quality: str) -> int:
        """统计背包条目里品质 >= min_quality 的数量。裸 int 视为 common。"""
        if isinstance(entry, dict):
            return sum(c for q, c in entry.items()
                       if self._qindex(q) >= self._qindex(min_quality))
        if isinstance(entry, int):
            return entry if self._qindex(min_quality) == 0 else 0
        return 0

    def check_materials(self, player: str, recipe: Recipe) -> bool:
        # fix1: 数量 + 品质双重检查，低品质材料不能造高品质物品
        inv = self.inventory.get(player, {})
        for item, (count, min_quality) in recipe.materials.items():
            if self._qualifying_count(inv.get(item, 0), min_quality) < count:
                return False
        return True

    def get_success_rate(self, player_skill: int, recipe: Recipe, tool: str = None) -> float:
        # fix2: 成功率 = 基础 + 技能等级与配方难度差 + 工具品质加成
        rate = recipe.success_rate + (player_skill - recipe.level) * 0.01
        if tool is not None:
            rate += TOOL_QUALITY_BONUS.get(self.tool_quality.get(tool, "common"), 0.0)
        return max(0.05, min(1.0, rate))

    def _has_space(self, inv: dict, item: str) -> bool:
        if not item or item in inv:
            return True
        return len(inv) < self.backpack_capacity

    def _consume_materials(self, player: str, recipe: Recipe) -> None:
        inv = self.inventory[player]
        for item, (count, min_quality) in recipe.materials.items():
            entry = inv[item]
            if isinstance(entry, dict):
                need = count
                for q in QUALITY_ORDER:  # 优先消耗刚好达标的低品质材料
                    if self._qindex(q) < self._qindex(min_quality):
                        continue
                    take = min(entry.get(q, 0), need)
                    entry[q] -= take
                    need -= take
                    if need == 0:
                        break
            else:
                inv[item] = entry - count

    def _roll_quality(self, recipe: Recipe, player_skill: int) -> int:
        # fix4: 属性范围受配方等级和制造者技能影响
        lo, hi = recipe.output_quality_range
        bonus = recipe.level // 5 + player_skill // 10
        return self.rng.randint(lo + bonus, hi + bonus)

    def craft(self, player: str, recipe_id: str, player_skill: int, tool: str = None) -> tuple[bool, str]:
        recipe = self.recipes[recipe_id]
        if not self.check_materials(player, recipe):
            return False, "no materials"
        inv = self.inventory.setdefault(player, {})
        # fix3: 原子检查背包空间，不足则直接失败，不扣材料
        if not self._has_space(inv, recipe.output):
            return False, "backpack full"
        rate = self.get_success_rate(player_skill, recipe, tool=tool)
        self._consume_materials(player, recipe)
        if self.rng.random() > rate:
            return False, "failed"
        quality = self._roll_quality(recipe, player_skill)
        if recipe.output:
            inv[recipe.output] = inv.get(recipe.output, 0) + 1
        return True, f"crafted_{recipe.output}_q{quality}"

    def can_learn(self, player_class: str, recipe: Recipe, player_faction: str = "") -> bool:
        # fix5: 职业 + 派系限制
        if recipe.faction and recipe.faction != player_faction:
            return False
        if recipe.allowed_classes:
            return player_class in recipe.allowed_classes
        allowed = PROFESSION_CLASSES.get(recipe.profession)
        if allowed is None:
            return False
        return player_class in allowed

    def gather(self, node_id: str, tool: str, zone: str = "default") -> dict:
        # fix6: 工具有耐久，耐久影响采集效率和产出品质
        max_durability = TOOL_DEFS.get(tool, {}).get("durability", 50)
        durability = self.tool_durability.setdefault(tool, max_durability)
        if durability <= 0:
            return {}  # 工具已损坏
        spec = TOOL_DEFS.get(tool, {"efficiency": 1.0, "quality_bonus": 0})
        wear = durability / max_durability
        self.tool_durability[tool] = durability - 1
        efficiency = spec["efficiency"] * (0.5 + 0.5 * wear)
        count = 1 + (1 if self.rng.random() < efficiency - 1.0 else 0)
        quality_idx = spec.get("quality_bonus", 0)
        if self.rng.random() < 0.2 * wear:
            quality_idx += 1
        quality = QUALITY_ORDER[min(quality_idx, len(QUALITY_ORDER) - 1)]
        return {"item": "ore", "count": count, "quality": quality, "zone": zone}

    def get_node_respawn(self, zone_population: int, zone: str = "default") -> float:
        # fix7: 动态刷新 = 基础 * 人口系数 * 区域系数，再加随机抖动防蹲点
        base = 60.0
        zone_factor = self.zone_modifiers.get(zone, 1.0)
        dynamic = base * (1.0 + 0.02 * max(0, zone_population)) * zone_factor
        return dynamic * self.rng.uniform(0.9, 1.1)
