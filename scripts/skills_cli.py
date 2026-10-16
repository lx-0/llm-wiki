"""`wiki skills install / uninstall / sync / status` (M034-S03-T06; was lib/skills.sh and the
bash `cmd_skills`, held to the bash oracle's skills-* goldens).

The engine ships its skills at .wiki/skills/<name>/ and links them into
<vault>/.claude/skills/<name> so Claude Code finds them. Only symlinks pointing at
../../.wiki/skills/<name> are the engine's; anything else under that name (the operator's
own skill, another tool's link) is never touched.

Global install: the skills in GLOBAL_SKILLS let an agent in any project discover and use a
wiki on this machine. With `skills.global_install` on, they are also linked into
~/.claude/skills/ (absolute targets: relative ones would not resolve from there), and the
vault is recorded in ${XDG_CONFIG_HOME:-~/.config}/llm-wiki/vaults for the skill's discovery
probe. Registry writes fail soft: a missing global link is recoverable, a hard error during
`wiki update` is not.

"This vault" is compared on resolved paths. The bash compared text, and its paths were the
ones `wiki` was started through; for a vault reached through a symlink it called its own
global link another vault's and `uninstall --global` left it behind.
"""

from __future__ import annotations

import contextlib
import io
import os
import sys
from pathlib import Path

from cli_help import H_SKILLS, print_help
from core import config as core_config
from core.console import banner, info, ok, print_error, warn
from core.paths import ROOT_DIR, WIKI_DIR

# The skills safe to link outside a vault — keep it tight; the others work inside one.
GLOBAL_SKILLS = ("use-llm-wiki",)
LINK_PREFIX = "../../.wiki/skills"


def _styled(text: str, code: str) -> str:
    return f"\033[{code}m{text}\033[0m" if sys.stdout.isatty() else text


def _src() -> Path:
    return WIKI_DIR / "skills"


def _dst() -> Path:
    return ROOT_DIR / ".claude" / "skills"


def _global_dst() -> Path:
    return Path.home() / ".claude" / "skills"


def _registry() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "llm-wiki" / "vaults"


def _entries(directory: Path) -> list[Path]:
    """What the bash glob `<dir>/*` listed: the non-hidden entries, sorted."""
    return sorted(p for p in directory.iterdir() if not p.name.startswith("."))


def _skills() -> list[str]:
    """The engine's skills: the directories under .wiki/skills/."""
    return [p.name for p in _entries(_src()) if p.is_dir()]


def _exists(path: Path) -> bool:
    return path.is_symlink() or path.exists()


def _engine_owned(link: Path) -> bool:
    return link.is_symlink() and os.readlink(link).startswith(f"{LINK_PREFIX}/")


def _same_path(a: str | Path, b: str | Path) -> bool:
    return Path(a).resolve() == Path(b).resolve()


def _global_enabled() -> bool:
    try:
        return core_config.value_of("skills.global_install", core_config.load()) is True
    except KeyError:
        return False


def _set_global(on: bool) -> None:
    """The opt-in, through config's validated `set` path; silent, as the bash's
    `config_set … >/dev/null` was."""
    with contextlib.redirect_stdout(io.StringIO()):
        core_config._cli(["set", "skills.global_install", "true" if on else "false"])


# ── Local links ────────────────────────────────────────────────────────────


def install_local() -> tuple[int, int, int]:
    """(added, already linked, foreign): the missing engine links are created; the engine's
    and anything foreign under a skill's name are left as they are."""
    if not _src().is_dir():
        return 0, 0, 0
    dst = _dst()
    dst.mkdir(parents=True, exist_ok=True)
    added = skipped = foreign = 0
    for name in _skills():
        link = dst / name
        if _engine_owned(link):
            skipped += 1
        elif _exists(link):
            foreign += 1
        else:
            link.symlink_to(f"{LINK_PREFIX}/{name}")
            added += 1
    return added, skipped, foreign


def prune_stale() -> int:
    """Engine links whose skill is gone from .wiki/skills/ (after an update)."""
    dst = _dst()
    if not dst.is_dir():
        return 0
    pruned = 0
    for link in _entries(dst):
        if _engine_owned(link) and not (_src() / link.name).is_dir():
            link.unlink()
            pruned += 1
    return pruned


# ── Global links and the registry ──────────────────────────────────────────


def _registry_lines() -> list[str]:
    return _registry().read_text(encoding="utf-8").splitlines()


def _registry_add() -> None:
    registry = _registry()
    try:
        registry.parent.mkdir(parents=True, exist_ok=True)
    except OSError:
        warn(f"cannot create {registry.parent} — vault not registered")
        return
    try:
        lines = _registry_lines() if registry.exists() else []
        if not any(line and _same_path(line, ROOT_DIR) for line in lines):
            with registry.open("a", encoding="utf-8") as fh:
                fh.write(f"{ROOT_DIR}\n")
    except OSError:
        warn(f"cannot write {registry} — vault not registered")


def _registry_remove() -> None:
    registry = _registry()
    if not registry.is_file():
        return
    with contextlib.suppress(OSError):
        kept = [line for line in _registry_lines() if not (line and _same_path(line, ROOT_DIR))]
        tmp = registry.with_name(f"{registry.name}.tmp")
        tmp.write_text("".join(f"{line}\n" for line in kept), encoding="utf-8")
        tmp.replace(registry)


def install_global() -> tuple[int, int, int]:
    """(added, already linked, foreign) in ~/.claude/skills/, then the vault registered. A
    link into any .wiki/skills/ is the engine's and stays: the skill is the same in every
    vault, and discovery reads the registry."""
    if not _src().is_dir():
        return 0, 0, 0
    global_dst = _global_dst()
    global_dst.mkdir(parents=True, exist_ok=True)
    added = skipped = foreign = 0
    for name in GLOBAL_SKILLS:
        target = _src() / name
        if not target.is_dir():
            continue
        link = global_dst / name
        if link.is_symlink():
            current = os.readlink(link)
            if _same_path(current, target) or "/.wiki/skills/" in current:
                skipped += 1
            else:
                foreign += 1
        elif link.exists():
            foreign += 1
        else:
            link.symlink_to(target)
            added += 1
    _registry_add()
    return added, skipped, foreign


def uninstall_global() -> int:
    """This vault's global links removed, and the vault deregistered; other vaults' links
    and foreign entries stay."""
    removed = 0
    global_dst = _global_dst()
    if global_dst.is_dir():
        for name in GLOBAL_SKILLS:
            link = global_dst / name
            if link.is_symlink() and _same_path(os.readlink(link), _src() / name):
                link.unlink()
                removed += 1
    _registry_remove()
    return removed


# ── The commands ───────────────────────────────────────────────────────────


def install(global_flag: bool | None) -> int:
    if global_flag is not None:
        _set_global(global_flag)
    banner("wiki skills install", "Symlink engine skills into .claude/skills/")
    added, skipped, foreign = install_local()
    if added:
        ok(f"linked {added} skill(s) into {_dst()}")
    if skipped:
        info(f"{skipped} skill(s) already linked")
    if foreign:
        warn(f"{foreign} name(s) collide with non-engine entries — left untouched")
        info("Run 'wiki skills status' to see which.")
    if added + skipped + foreign == 0:
        info(f"no skills found in {_src()} — nothing to do")
    if _global_enabled():
        print()
        g_added, g_skipped, g_foreign = install_global()
        info("global install (skills.global_install: true)")
        if g_added:
            ok(f"linked {g_added} skill(s) into {_global_dst()}")
        if g_skipped:
            info(f"{g_skipped} global skill(s) already linked")
        if g_foreign:
            warn(f"{g_foreign} global name(s) collide with non-engine entries — left untouched")
        info(f"vault registered in {_registry()}")
    return 0


def uninstall(global_flag: bool | None) -> int:
    banner("wiki skills uninstall", "Remove engine-owned symlinks only")
    dst = _dst()
    if not dst.is_dir():
        info(f"no {dst} — nothing to do")
    else:
        removed = 0
        for link in _entries(dst):
            if _engine_owned(link):
                link.unlink()
                removed += 1
        if removed:
            ok(f"removed {removed} engine-owned symlink(s)")
        else:
            info("no engine-owned symlinks found")
    if global_flag:
        _set_global(False)
        removed = uninstall_global()
        print()
        if removed:
            ok(f"removed {removed} global symlink(s) from {_global_dst()}")
        else:
            info("no global symlinks for this vault")
        info(f"vault deregistered from {_registry()}; skills.global_install set false")
    return 0


def sync() -> int:
    """`wiki update`'s post-step: install the missing, prune the stale, and with the global
    opt-in on refresh the global links too. One summary line."""
    added, _skipped, foreign = install_local()
    pruned = prune_stale()
    global_added = install_global()[0] if _global_enabled() else 0
    if not (added or pruned or foreign or global_added):
        info("skills: up to date")
        return 0
    parts = ["skills:"]
    if added:
        parts.append(f"+{added} linked")
    if pruned:
        parts.append(f"-{pruned} pruned")
    if foreign:
        parts.append(f"{foreign} collision(s)")
    if global_added:
        parts.append(f"+{global_added} global")
    ok(" ".join(parts))
    return 0


def status() -> int:
    banner("wiki skills status")
    print(f"{'SKILL':<32} STATE")
    print("─" * 62)
    src, dst = _src(), _dst()
    if not src.is_dir():
        info(f"no {src} directory")
        return 0
    for name in _skills():
        link = dst / name
        if _engine_owned(link):
            state = _styled("linked", "32")
        elif _exists(link):
            state = f"{_styled('collision', '33')} (foreign entry — not managed)"
        else:
            state = _styled("missing", "2")
        print(f"{name:<32} {state}")
    if dst.is_dir():
        stale = [
            link.name
            for link in _entries(dst)
            if _engine_owned(link) and not (src / link.name).is_dir()
        ]
        if stale:
            print()
            warn("stale engine-owned symlinks (source no longer exists):")
            for name in stale:
                print(f"  {name}")
            info("Run 'wiki skills sync' to prune them.")
    print()
    if _global_enabled():
        print(f"{'GLOBAL INSTALL':<32} {_styled('on', '32')}  (skills.global_install)")
    else:
        hint = "(skills.global_install — wiki skills install --global)"
        print(f"{'GLOBAL INSTALL':<32} {_styled('off', '2')} {hint}")
    for name in GLOBAL_SKILLS:
        link = _global_dst() / name
        if link.is_symlink():
            current = os.readlink(link)
            if _same_path(current, src / name):
                state = f"{_styled('linked', '32')} → this vault"
            elif "/.wiki/skills/" in current:
                state = f"{_styled('linked', '33')} → other vault ({current})"
            else:
                state = f"{_styled('collision', '33')} (foreign entry — not managed)"
        elif link.exists():
            state = f"{_styled('collision', '33')} (foreign entry — not managed)"
        else:
            state = _styled("not linked", "2")
        print(f"  {name:<30} {state}")
    registry = _registry()
    if registry.is_file():
        print(f"  {'registry':<30} {registry}")
        for vault in _registry_lines():
            if not vault:
                continue
            if os.access(Path(vault) / ".wiki" / "wiki", os.X_OK):
                print(f"    {_styled('✓', '32')} {vault}")
            else:
                print(f"    {_styled('!', '33')} {vault} {_styled('(stale — no .wiki/wiki)', '2')}")
    else:
        print(f"  {'registry':<30} {_styled(f'none ({registry})', '2')}")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    # --global / --no-global may stand anywhere; the rest names the command
    global_flag: bool | None = None
    rest: list[str] = []
    for arg in args:
        if arg == "--global":
            global_flag = True
        elif arg == "--no-global":
            global_flag = False
        else:
            rest.append(arg)
    command = rest[0] if rest else "install"
    if command == "install":
        return install(global_flag)
    if command == "uninstall":
        return uninstall(global_flag)
    if command == "sync":
        return sync()
    if command == "status":
        return status()
    print_error(f"unknown: wiki skills {command}")
    print_help(H_SKILLS)
    return 1


if __name__ == "__main__":
    sys.exit(main())
