from src.live_client import build_match_context


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

