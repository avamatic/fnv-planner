from scripts.plan_build import _goal_from_dict, _starting_from_dict


def test_goal_from_dict_parses_hex_and_flags():
    goal = _goal_from_dict(
        {
            "required_perks": ["0x1000", 4097],
            "requirements": [
                {
                    "kind": "actor_value",
                    "actor_value": "science",
                    "operator": ">=",
                    "value": 90,
                    "priority": 300,
                    "reason": "science perk gate",
                    "by_level": 16,
                },
                {
                    "kind": "perk",
                    "perk_id": "0x1337",
                    "perk_rank": 1,
                    "priority": 200,
                    "reason": "dialogue perk check",
                },
                {
                    "kind": "trait",
                    "trait_id": "0x1444",
                    "priority": 150,
                    "reason": "modded trait requirement",
                },
                {
                    "kind": "max_skills",
                    "priority": 125,
                    "reason": "completionist",
                },
            ],
            "target_level": "30",
            "maximize_skills": True,
            "fill_perk_slots": False,
        }
    )
    assert goal.required_perks == [0x1000, 4097]
    assert len(goal.requirements) == 4
    assert goal.requirements[0].kind == "actor_value"
    assert goal.requirements[0].actor_value == 40
    assert goal.requirements[1].kind == "perk"
    assert goal.requirements[1].perk_id == 0x1337
    assert goal.requirements[2].kind == "trait"
    assert goal.requirements[2].trait_id == 0x1444
    assert goal.requirements[3].kind == "max_skills"
    assert goal.target_level == 30
    assert goal.maximize_skills is True
    assert goal.fill_perk_slots is False


def test_starting_from_dict_parses_named_actor_values():
    start = _starting_from_dict(
        {
            "sex": 0,
            "special": {
                "strength": 7,
                "perception": 7,
                "endurance": 6,
                "charisma": 6,
                "intelligence": 5,
                "agility": 5,
                "luck": 4,
            },
            "tagged_skills": ["guns", "lockpick", "speech"],
            "equipment": {"1": "0xdeadbeef"},
        }
    )
    assert start.sex == 0
    assert start.special is not None
    assert start.special[5] == 7
    assert start.tagged_skills == {41, 36, 43}
    assert start.equipment == {1: 0xDEADBEEF}
