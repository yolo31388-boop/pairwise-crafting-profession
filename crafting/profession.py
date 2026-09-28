"""生活技能与制造系统 - 含7个bug"""
import random
from dataclasses import dataclass, field

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

class CraftingSystem:
    def __init__(self, seed: int = 42):
        self.rng = random.Random(seed)
        self.recipes: dict[str, Recipe] = {}
        self.inventory: dict[str, dict] = {}  # player -> {item: count}
        self.backpack_capacity = 20
        self.tool_durability: dict[str, int] = {}

    def check_materials(self, player: str, recipe: Recipe) -> bool:
        # bug1: 只看数量不看品质
        for item, (count, _) in recipe.materials.items():
            if self.inventory.get(player, {}).get(item, 0) < count:
                return False
        return True

    def get_success_rate(self, player_skill: int, recipe: Recipe) -> float:
        # bug2: 固定成功率
        return recipe.success_rate

    def craft(self, player: str, recipe_id: str, player_skill: int) -> tuple[bool, str]:
        recipe = self.recipes[recipe_id]
        if not self.check_materials(player, recipe):
            return False, "no materials"
        # bug3: 背包满时扣了材料
        rate = self.get_success_rate(player_skill, recipe)
        # 先扣材料
        for item, (count, _) in recipe.materials.items():
            self.inventory[player][item] -= count
        if self.rng.random() > rate:
            return False, "failed"
        # bug4: 属性范围不受配方等级影响
        quality = self.rng.randint(*recipe.output_quality_range)
        return True, f"crafted_{recipe.output}_q{quality}"

    def can_learn(self, player_class: str, recipe: Recipe) -> bool:
        # bug5: 无职业限制
        return True

    def gather(self, node_id: str, tool: str) -> dict:
        # bug6: 工具无耐久
        return {"item": "ore", "count": 1}

    def get_node_respawn(self, zone_population: int) -> float:
        # bug7: 固定刷新
        return 60.0
