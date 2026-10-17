from copy import deepcopy

from src.live_client import (
    build_match_context,
    build_roster_key,
    champion_id_from_raw,
    is_static_roster_ready,
    sanitize_live_data,
)


def test_build_match_context_identifies_active_player_and_teams():
    snapshot = {
        "activeplayer": {"riotId": "Self#TAG"},
        "gamestats": {"gameMode": "CLASSIC"},
        "playerlist": [
            {
                "riotId": "Self#TAG",
                "championName": "Vayne",
                "rawChampionName": "game_character_displayname_Vayne",
                "team": "ORDER",
                "position": "BOTTOM",
                "isBot": False,
                "level": 5,
            },
            {
                "riotId": "Brand#BOT",
                "championName": "Brand",
                "rawChampionName": "game_character_displayname_Brand",
                "team": "CHAOS",
                "position": "MIDDLE",
                "isBot": True,
                "level": 5,
            },
        ],
    }

    context = build_match_context(snapshot)

    assert context["active_player"]["champion_id"] == "Vayne"
    assert context["active_player"]["champion_slug"] == "vayne"
    assert [p["champion_id"] for p in context["allies"]] == ["Vayne"]
    assert [p["champion_id"] for p in context["enemies"]] == ["Brand"]
    assert context["allies"][0]["is_active"] is True


def test_champion_id_from_raw_supports_both_riot_formats():
    assert champion_id_from_raw("game_character_displayname_Ashe") == "Ashe"
    assert champion_id_from_raw("Character_Aatrox_Name") == "Aatrox"


def test_sanitize_live_data_keeps_only_static_pregame_fields():
    raw = {
        "activeplayer": {"riotId": "Self#TW2", "currentGold": 900},
        "activeplayername": "Self#TW2",
        "playerlist": [
            {
                "riotId": "Self#TW2",
                "championName": "Ashe",
                "rawChampionName": "game_character_displayname_Ashe",
                "team": "ORDER",
                "position": "NONE",
                "isBot": False,
                "level": 8,
                "items": [{"itemID": 3031}],
                "scores": {"kills": 3},
            }
        ],
        "gamestats": {"gameMode": "ARAM", "mapNumber": 12, "gameTime": 300},
        "eventdata": {"Events": [{"EventName": "ChampionKill"}]},
    }

    sanitized = sanitize_live_data(raw)

    assert sanitized["activeplayer"] == {}
    assert sanitized["activeplayername"] == ""
    assert sanitized["gamestats"] == {"gameMode": "ARAM", "mapNumber": 12}
    assert "eventdata" not in sanitized
    assert sanitized["playerlist"][0] == {
        "championName": "Ashe",
        "rawChampionName": "game_character_displayname_Ashe",
        "team": "ORDER",
        "position": "NONE",
        "isBot": False,
        "isActivePlayer": True,
    }


def _full_roster_snapshot():
    players = []
    for index, champion in enumerate(["Ashe", "Garen", "Lux", "Nami", "XinZhao"]):
        players.append(
            {
                "riotId": "Self#TW2" if index == 0 else f"Ally{index}#TW2",
                "championName": champion,
                "rawChampionName": f"game_character_displayname_{champion}",
                "team": "ORDER",
            }
        )
    for index, champion in enumerate(["Brand", "Jax", "Zyra", "Corki", "Kindred"]):
        players.append(
            {
                "riotId": f"Enemy{index}#TW2",
                "championName": champion,
                "rawChampionName": f"game_character_displayname_{champion}",
                "team": "CHAOS",
            }
        )
    return {
        "activeplayer": {"riotId": "Self#TW2"},
        "gamestats": {"gameMode": "ARAM", "mapNumber": 12, "gameTime": 10},
        "playerlist": players,
    }


def test_static_roster_requires_all_ten_players_and_active_identity():
    complete = _full_roster_snapshot()
    incomplete = deepcopy(complete)
    incomplete["playerlist"].pop()

    assert is_static_roster_ready(complete)
    assert not is_static_roster_ready(incomplete)


def test_roster_key_does_not_change_with_game_time():
    initial = _full_roster_snapshot()
    later = deepcopy(initial)
    later["gamestats"]["gameTime"] = 95

    assert build_roster_key(initial) == build_roster_key(later)
