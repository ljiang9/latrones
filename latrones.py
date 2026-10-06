#!/usr/bin/env python3
"""Latrones —— 古罗马军棋（Ludus latrunculorum）的重构版。

历史规则已失传，这里采用常见的重构规则（README 诚实说明）：
- 8x8 棋盘，双方各 16 子，开局摆在己方底线两行。
- 棋子像国际象棋车一样横竖走任意格，不能跳子。
- 夹吃（custodian）：走子后，若某敌子在横/竖方向上被你的两子夹住
  （紧邻两侧），则被吃掉。主动走进两敌子之间不算自杀。
- 吃光对方全部棋子，或对方无合法走法，即获胜。

纯标准库，Python 3.10+。
"""

import argparse
import copy
import random
import sys

SIZE = 8
EMPTY = "."
P0 = "甲"  # 先手
P1 = "乙"  # 后手
PIECES_PER_SIDE = 16
DIRS = ((1, 0), (-1, 0), (0, 1), (0, -1))
MAX_MOVES = 600  # 防无限对局的半回合上限


def other(player):
    return P1 if player == P0 else P0


def in_bounds(r, c):
    return 0 <= r < SIZE and 0 <= c < SIZE


def initial_board():
    b = [[EMPTY] * SIZE for _ in range(SIZE)]
    for r in range(2):
        for c in range(SIZE):
            b[r][c] = P0
    for r in range(SIZE - 2, SIZE):
        for c in range(SIZE):
            b[r][c] = P1
    return b


def capture_squares(board, player, tr, tc):
    """走子落到 (tr,tc) 后被夹吃的敌子坐标（纯函数，不改棋盘）。

    规则：敌子 (nr,nc) 与落子 (tr,tc) 紧邻，且另一侧 (br,bc) 是我方子，
    则 (nr,nc) 被吃。只在横竖方向判定。
    """
    foe = other(player)
    caps = []
    for dr, dc in DIRS:
        nr, nc = tr + dr, tc + dc
        br, bc = nr + dr, nc + dc
        if (in_bounds(nr, nc) and in_bounds(br, bc)
                and board[nr][nc] == foe
                and board[br][bc] == player):
            caps.append((nr, nc))
    return caps


class Latrones:
    def __init__(self, seed=None):
        self.board = initial_board()
        self.rng = random.Random(seed)
        self.n_moves = 0

    # ---- 走法 ----

    def _rook_rays(self, board, r, c):
        """从 (r,c) 出发横竖四个方向的空位射线走法。"""
        out = []
        for dr, dc in DIRS:
            nr, nc = r + dr, c + dc
            while in_bounds(nr, nc) and board[nr][nc] == EMPTY:
                out.append((nr, nc))
                nr, nc = nr + dr, nc + dc
        return out

    def legal_moves(self, player):
        moves = []
        for r in range(SIZE):
            for c in range(SIZE):
                if self.board[r][c] == player:
                    for dst in self._rook_rays(self.board, r, c):
                        moves.append(((r, c), dst))
        return moves

    def _check_move(self, player, move):
        (fr, fc), (tr, tc) = move
        if not (in_bounds(fr, fc) and in_bounds(tr, tc)):
            raise ValueError(f"走法越界: {move}")
        if self.board[fr][fc] != player:
            raise ValueError(f"起点不是你的棋子: {move}")
        if self.board[tr][tc] != EMPTY:
            raise ValueError(f"落点被占: {move}")
        dr, dc = tr - fr, tc - fc
        if not ((dr == 0) != (dc == 0)):
            raise ValueError(f"必须横走或竖走: {move}")
        step_r = 0 if dr == 0 else (1 if dr > 0 else -1)
        step_c = 0 if dc == 0 else (1 if dc > 0 else -1)
        r, c = fr + step_r, fc + step_c
        while (r, c) != (tr, tc):
            if self.board[r][c] != EMPTY:
                raise ValueError(f"路径被挡: {move}")
            r, c = r + step_r, c + step_c

    def apply_move(self, player, move):
        """执行走法，返回吃掉的敌子数。非法走法抛 ValueError。"""
        self._check_move(player, move)
        (fr, fc), (tr, tc) = move
        self.board[fr][fc] = EMPTY
        self.board[tr][tc] = player
        caps = capture_squares(self.board, player, tr, tc)
        for r, c in caps:
            self.board[r][c] = EMPTY
        self.n_moves += 1
        return len(caps)

    # ---- 状态 ----

    def count(self, player):
        return sum(row.count(player) for row in self.board)

    def winner(self):
        """返回 P0/P1 表示获胜方；None 表示对局继续。"""
        if self.count(P0) == 0:
            return P1
        if self.count(P1) == 0:
            return P0
        return None

    def copy(self):
        g = Latrones.__new__(Latrones)
        g.board = [row[:] for row in self.board]
        g.rng = self.rng
        g.n_moves = self.n_moves
        return g


# ---- AI ----

def ai_choose(game, player):
    """贪心：吃子最多优先；否则走靠近敌子的走法；平局随机。"""
    moves = game.legal_moves(player)
    if not moves:
        return None
    foe = other(player)
    foe_pos = [(r, c) for r in range(SIZE) for c in range(SIZE)
               if game.board[r][c] == foe]
    best, best_key = None, None
    for mv in moves:
        sim = game.copy()
        caps = sim.apply_move(player, mv)
        (tr, tc) = mv[1]
        dist = min((abs(tr - r) + abs(tc - c) for r, c in foe_pos),
                   default=0)
        key = (caps, -dist, game.rng.random())
        if best_key is None or key > best_key:
            best_key, best = key, mv
    return best


# ---- 对局 ----

def play_auto(games=10, seed=42, verbose=False):
    rng = random.Random(seed)
    tally = {P0: 0, P1: 0, "draw": 0}
    for i in range(games):
        g = Latrones(seed=rng.randrange(1 << 30))
        turn = P0
        result = None
        while g.n_moves < MAX_MOVES:
            mv = ai_choose(g, turn)
            if mv is None:
                result = other(turn)  # 无棋可走判负
                break
            caps = g.apply_move(turn, mv)
            if verbose:
                print(f"  {turn} {mv[0]}->{mv[1]} 吃{caps}子")
            w = g.winner()
            if w is not None:
                result = w
                break
            turn = other(turn)
        else:
            result = "draw"
        if result == "draw":
            tally["draw"] += 1
            if verbose:
                print(f"第 {i+1}/{games} 局：和棋")
        else:
            tally[result] += 1
            if verbose:
                print(f"第 {i+1}/{games} 局：{result}胜")
    print(f"总计：{P0}胜 {tally[P0]}，{P1}胜 {tally[P1]}，和棋 {tally['draw']}")
    return tally


# ---- 文本界面 ----

GLYPH = {EMPTY: "·", P0: "甲", P1: "乙"}


def render(game):
    head = "  " + " ".join(f"{c}" for c in range(SIZE))
    lines = [head]
    for r in range(SIZE):
        lines.append(f"{r} " + " ".join(GLYPH[game.board[r][c]]
                                       for c in range(SIZE)))
    return "\n".join(lines)


def parse_coord(s):
    try:
        r, c = s.split(",")
        r, c = int(r), int(c)
    except ValueError:
        raise ValueError("坐标格式应为 行,列，如 1,3")
    if not in_bounds(r, c):
        raise ValueError("坐标越界")
    return r, c


def play_interactive():
    if not sys.stdin.isatty():
        print("交互模式需要终端；无头演示请用 --auto", file=sys.stderr)
        return 2
    g = Latrones()
    turn = P0
    print("Latrones 古罗马军棋：走法如车（横竖直走，不能跳子）；"
          "夹吃敌子；吃光或困死对方获胜。")
    print("输入如 1,3 5,3 表示把 (1,3) 走到 (5,3)；q 退出。")
    while True:
        print(render(g))
        print(f"{turn} 行棋，{P0}剩{g.count(P0)} {P1}剩{g.count(P1)}")
        mv = ai_choose(g, turn)
        if mv is None:
            print(f"{turn} 无棋可走，{other(turn)} 获胜！")
            return 0
        try:
            s = input("> ").strip()
        except EOFError:
            print()
            return 0
        if s.lower() == "q":
            return 0
        try:
            a, b = s.split()
            move = (parse_coord(a), parse_coord(b))
            caps = g.apply_move(turn, move)
        except ValueError as e:
            print(f"非法走法：{e}")
            continue
        if caps:
            print(f"夹吃 {caps} 子！")
        w = g.winner()
        if w is not None:
            print(render(g))
            print(f"{w} 获胜！")
            return 0
        turn = other(turn)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Latrones 古罗马军棋（重构规则）")
    ap.add_argument("--auto", action="store_true", help="AI 对 AI 自动演示")
    ap.add_argument("--games", type=int, default=10, help="自动演示局数")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--verbose", action="store_true", help="自动演示打印每步")
    args = ap.parse_args(argv)
    if args.auto:
        play_auto(games=args.games, seed=args.seed, verbose=args.verbose)
        return 0
    return play_interactive()


if __name__ == "__main__":
    raise SystemExit(main())
