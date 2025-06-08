from fastapi import FastAPI, WebSocket, HTTPException
from pydantic import BaseModel
from email_validator import validate_email, EmailNotValidError
from uuid import uuid4
from typing import List, Optional
from game import Game, Player
from pydantic import BaseModel, EmailStr
from fastapi.middleware.cors import CORSMiddleware
import json

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_creditials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

active_connections = {}
games = {}
users = {}


class GameStateUpdate(BaseModel):
    action: str
    data: dict


@app.websocket("/ws/game/{game_code}")
async def websocket_endpoint(websocket: WebSocket, game_code: str):
    await websocket.accept()

    if game_code not in active_connections:
        active_connections[game_code] = []
    active_connections[game_code].append(websocket)

    try:
        while True:
            data = await websocket.receive_text()
            print(f"Сообщение от клиента: {data}")

    except Exception as e:
        active_connections[game_code].remove(websocket)
        if not active_connections[game_code]:
            del active_connections[game_code]


class User(BaseModel):
    id: str
    email: str
    password: str
    name: str
    online: bool = False


class RegisterReq(BaseModel):
    email: EmailStr
    name: str
    password: str


class LoginReq(BaseModel):
    email: EmailStr
    password: str


class JoinGame(BaseModel):
    player_id: str
    join_password: str


class CreateGame(BaseModel):
    creator_id: str


class StartGame(BaseModel):
    creator_id: str
    join_password: str


class PlayCard(BaseModel):
    player_id: str
    join_password: str
    cards: List[str]


class DefendCard(BaseModel):
    player_id: str
    join_password: str
    card_attack: str
    card_defense: str


class StateOfGame(BaseModel):
    join_password: str
    count_players: int
    deck_count: int
    players: List[str]
    curr_turn: Optional[str] = None
    card_on_table: List[List[Optional[str]]]


@app.post("/register")
def register(req: RegisterReq):
    for u in users.values():
        if u.email == req.email:
            raise HTTPException(status_code=404, detail="Такой email уже зарегестрирован")
    user_id = str(uuid4())
    new_user = User(
        id=user_id,
        email=req.email,
        password=req.password,
        name=req.name,
        online=True
    )
    users[user_id] = new_user
    return {"user_id": user_id, "message": "Регистрация прошла успешна"}


# guid
@app.post("/login")
def login(req: LoginReq):
    for user in users.values():
        if user.email == req.email and user.password == req.password:
            user.online = True
            return {"user_id": user.id, "message": "Авторизация прошла успешно"}
    raise HTTPException(status_code=401, detail="Неверные учетные данные")


@app.post("/game/new")
def game_creation(req: CreateGame):
    creator = users.get(req.creator_id)
    if not creator:
        raise HTTPException(status_code=404, detail="Такого создателя не найдено")
    player = Player(player_id=creator.id, name=creator.name, email=creator.email)
    game = Game(creator=player)
    games[game.join_password] = game
    return {
        "game_code_join": game.join_password,
        "message": "Игра создана. Подключение только по коду от создателя"
    }


@app.post("/game/join")
def join_to_game(req: JoinGame):
    if req.join_password not in games:
        raise HTTPException(status_code=404, detail="Игра не найдена")
    if req.player_id not in users:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    user = users[req.player_id]
    game = games[req.join_password]
    if game.started:
        raise HTTPException(status_code=400, detail="Игра уже идет")
    new_player = Player(player_id=user.id, name=user.name, email=user.email)
    try:
        game.add_player(new_player)
    except Exception as ex:
        raise HTTPException(status_code=404, detail=str(ex))
    return {"message": f"{user.name} вошел в игру",
            "num_players": len(game.players)
            }


@app.post("/game/start")
def start_game(req: StartGame):
    if req.join_password not in games:
        raise HTTPException(status_code=404, detail="Такая игра не найдена")
    game = games[req.join_password]
    if game.creator.id != req.creator_id:
        raise HTTPException(status_code=403, detail="Игру может начать только создатель")
    try:
        game.start_game()
    except Exception as ex:
        raise HTTPException(status_code=400, detail=str(ex))
    return {
        "message": "Игра запущена",
        "curr_turn": game.curr_turn,
        "trump": game.trump.card_str if game.trump else None
    }


@app.post("/game/play")
def pay_card(req: PlayCard):
    if req.join_password not in games:
        raise HTTPException(status_code=404, detail="Игра не найдена")
    game = games[req.join_password]
    player = next((pl for pl in game.players if pl.id == req.player_id), None)
    if not player:
        raise HTTPException(status_code=404, detail="Такой игрок не найден")
    try:
        game.player_cards(player, req.cards)
        game.replace_hand(player)
    except Exception as ex:
        raise HTTPException(status_code=400, detail=str(ex))
    return {
        "message": f"Игрок {player.name} сыграл {req.cards}",
        "next_turn": game.curr_turn
    }


@app.post("/games/defend")
def defend_card(req: DefendCard):
    if req.join_password not in games:
        raise HTTPException(status_code=404, detail="Игра не найдена")
    game = games[req.join_password]
    player = next((pl for pl in game.players if pl.id == req.player_id), None)
    if not player:
        raise HTTPException(status_code=404, detail="Такой игрок не найден")
    try:
        game.defend_card(req.card_attack, req.card_defense, player)
    except Exception as ex:
        raise HTTPException(status_code=400, detail=str(ex))
    return {
        "message": f"Игрок {player.name} отбил карту {req.card_attack} картой {req.card_defense}"
    }


@app.get("/games/state/{join_password}", response_model=StateOfGame)
def state_of_game(join_password: str):
    if join_password not in games:
        raise HTTPException(status_code=404, detail="Данная игра не найдена")
    game = games[join_password]
    names_of_players = [pl.name for pl in game.players]
    table = []
    for attack, defense in game.cards_on_table:
        attack_str = attack.card_str if attack else None
        defense_str = defense.card_str if defense else None
        table.append([attack_str, defense_str])
    return StateOfGame(
        join_password=join_password,
        count_players=len(game.players),
        deck_count=len(game.deck),
        players=names_of_players,
        curr_turn=game.curr_turn,
        card_on_table=table
    )
