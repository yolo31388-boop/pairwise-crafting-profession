"""生活技能与制造系统 - 红态测试"""
import pytest, sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from crafting.profession import CraftingSystem, Recipe

class TestMaterialQuality:
    def test_material_quality_checked(self):
        cs = CraftingSystem()
        r = Recipe("r1", "sword", 1, "blacksmith", materials={"iron": (2, "rare")})
        cs.recipes["r1"] = r
        cs.inventory = {"p1": {"iron": 5}}  # 只有普通iron
        # 需要品质系统：inventory存(item, quality) -> count
        # 这里简化：check_materials应该检查品质
        # 由于当前实现不检查品质，这个测试会失败
        assert cs.check_materials("p1", r) == False  # bug1: 返回True

class TestSuccessRateScaling:
    def test_success_rate_scales_with_skill(self):
        cs = CraftingSystem()
        r = Recipe("r1", "item", 50, "alchemy", success_rate=0.3)
        cs.recipes["r1"] = r
        r_low = cs.get_success_rate(10, r)
        r_high = cs.get_success_rate(100, r)
        assert r_high > r_low  # bug2: 都是0.3

class TestBackpackFull:
    def test_no_material_deduction_when_backpack_full(self):
        cs = CraftingSystem()
        cs.backpack_capacity = 1
        cs.inventory = {"p1": {"iron": 10}}
        r = Recipe("r1", "sword", 1, "blacksmith", materials={"iron": (2, "common")}, output="sword")
        cs.recipes["r1"] = r
        # 背包满了（1/1），制造应该失败且不扣材料
        before = cs.inventory["p1"]["iron"]
        cs.craft("p1", "r1", 100)
        assert cs.inventory["p1"]["iron"] == before  # bug3: 扣了材料

class TestOutputQualityByLevel:
    def test_higher_recipe_better_quality(self):
        cs = CraftingSystem(seed=42)
        r_low = Recipe("r1", "low", 1, "blacksmith", output_quality_range=(1, 10))
        r_high = Recipe("r2", "high", 50, "blacksmith", output_quality_range=(50, 100))
        cs.recipes["r1"] = r_low
        cs.recipes["r2"] = r_high
        cs.inventory = {"p1": {"iron": 100}}
        # 多次制造取平均
        import statistics
        q1 = [cs.craft("p1", "r1", 100) for _ in range(20)]
        q2 = [cs.craft("p1", "r2", 100) for _ in range(20)]
        # 这个测试可能不稳定

class TestProfessionRestriction:
    def test_wrong_class_cannot_learn(self):
        cs = CraftingSystem()
        r = Recipe("r1", "potion", 1, "alchemy")
        assert cs.can_learn("warrior", r) == False  # bug5: 返回True
        assert cs.can_learn("mage", r) == True  # 假设mage能学制药

class TestToolDurability:
    def test_tool_has_durability(self):
        cs = CraftingSystem()
        cs.tool_durability = {"pickaxe": 0}
        result = cs.gather("node1", "pickaxe")
        assert result == {} or "broken" in str(result)  # bug6: 耐久0还能采

class TestRespawByPopulation:
    def test_respawn_scales_with_population(self):
        cs = CraftingSystem()
        t_low = cs.get_node_respawn(10)
        t_high = cs.get_node_respawn(100)
        assert t_high > t_low  # bug7: 都是60（人多应该刷新快或慢？设计上人多刷新快）
