from uuid import uuid4
from typing import List, Optional
import random
import time
import threading
import os

class Card:
    def __init__(self, card_str: str):
        self.card_str = card_str
        self.rank = card_str[:-1]
        self.suit = card_str[-1]

    def __str__(self):
        return self.card_str

    def __repr__(self):
        return self.card_str

class Player:
    def __init__(self, player_id: str, name: str, email: str):
        self.id = player_id
        self.name = name
        self.email = email
        self.hand: List[Card] = []
        self.online: bool = False
        self.exited: bool = False
        self.lock = threading.Lock()

    def recive_card(self, cards: List[Card]) -> None:
        self.hand.extend(cards)

    def play_card(self, card_str: str) -> Card:
        with self.lock:
            for card in self.hand:
                if card.card_str == card_str:
                    self.hand.remove(card)
                    return card
        raise Exception(f"У игрока нет такой карты {card_str}")


class Game:
    passwords = set()
    def __init__(self, creator: Player):
        self.id = str(uuid4())
        self.join_password = self.unique_password()
        self.creator = creator
        self.players: List[Player] = [creator]
        self.started: bool = False
        self.deck: List[Card] = self.generate_deck()
        self.trump: Optional[Card] = None
        self.curr_turn: Optional[str] = None
        self.cards_on_table: List[List[Optional[Card]]] = []
        self.lock_table = threading.Lock()
        self.semaphore = threading.Semaphore(1)
        self.timer_defend = None
        self.player_defend = None


    def uniqie_password(self):
        while True:
            password = ''.join(str(random.randint(0, 9)) for _ in range(8))
            if password not in Game.passwords:
                Game.passwords.add(password)
                return password


    def generate_deck(self) -> List[Card]:
        suits = ['H', 'D', 'S', 'C']
        ranks = ['6', '7', '8', '9', '10', 'J', 'Q', 'K', 'A']
        deck = [Card(r + s) for s in suits for r in ranks]
        random.shuffle(deck)
        return deck

    def add_player(self, player: Player) -> None:
        if self.started:
            raise Exception("Игра уже началась. Нельзя подключиться")
        if len(self.players) >= 6:
            raise Exception("Количество игроков достигло максимума")
        self.players.append(player)

    def game_start(self) -> None:
        if self.started:
            raise Exception("Игра началась")
        self.started = True

        if self.deck:
            self.trump = self.deck[-1]
            self.deck.pop()

        for player in self.players:
            cards_need = 6 - len(player.hand)
            for _ in range(cards_need):
                if self.deck:
                    player.recive_card([self.deck.pop(0)])
        self.curr_turn = self.creator.id

    def replace_hand(self, player: Player) -> None:
        card_need = 6 - len(player.hand)
        for _ in range(card_need):
            if self.deck:
                player.recive_card([self.deck.pop(0)])

    def player_cards(self, player: Player, card_str: List[str]) -> None:
        with self.semaphore:
            with self.lock_table:
                if not self.cards_on_table and len(set(card_str)) > 1:
                    raise Exception("Нельзя класть карты, пока стол пустой")
                if self.curr_turn != player.id:
                   raise Exception("Сейчас не ваш ход")
                player_card = []
                for cs in card_str:
                    card = next((c for c in player.hand if c.card_str == cs), None)
                    if not card:
                        raise Exception(f"У игрока не имеется карты {cs}")
                    player.hand.remove(card)
                    self.cards_on_table.append([card, None])
                curr_ind = self.players.index(player)
                next_ind  = (curr_ind + 1) % len(self.players)
                self.curr_turn = self.players[next_ind].id


    def timer_defense(self):
        def timer():
            time.sleep(15)
            print("Время вышло. Если игрок не берет карты, то они идут в бито")

        self.timer_defense = threading.Thread(target=timer)
        self.timer_defense.start()


    def card_defend(self, attack_card: Card, card_defense: Card) -> bool:
        if card_defense.suit == attack_card.suit and self.value_rank(card_defense) > self.value_rank(attack_card):
            return True
        if card_defense.suit == self.trump.suit and attack_card.suit != self.trump.suit:
            return True
        return False

    def value_rank(self, card: Card) -> int:
        value = ['6', '7', '8', '9', '10', 'J', 'Q', 'K', 'A']
        return value.index(card.rank)

    def player_authenticate(self, email: str, password: str) -> bool:
        file = "user.txt"
        if not os.path.exists(file):
            raise Exception("Файл с пользователями не найден")
        with open(file, "r") as f:
            for line in f:
                emails_saved, passwords_saved = line.strip().split(":")
                if emails_saved == email and passwords_saved == password:
                    return True
        return False
    
    
    def get_state(self):
        return {
            "game_id": self.id,
            "join_password": self.join_password,
            "players": [p.name for p in self.players],
            "trump": str(self.trump) if self.trump else None,
            "curr_trun": self.curr_turn,
            "table": [[str(a), str(d)] for a, d in self.cards_on_table],
            "deck": len(self.deck)
        }
    
    
    def game_over(self) -> bool:
        for player in self.players:
            if not player.hand:
                return True
        return False
