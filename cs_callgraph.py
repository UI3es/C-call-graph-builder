"""
cs_callgraph.py  —  C# call graph builder → PlantUML

Положи рядом с .cs файлами. Запусти через PyCharm (Run / F5).
Результат: map.puml рядом со скриптом.

═══════════════════════════════════════════════════════════════════
ОБЪЯВЛЕНИЯ — всё что парсится
═══════════════════════════════════════════════════════════════════
Методы:
  void Foo() { }
  public static int Bar(int x) { }
  async Task Baz() { }
  int Qux() => expr;                   ← expression body
  T Generic<T>() where T : class { }
  ~MyClass() { }                       ← деструктор
  operator +(A a, B b) { }            ← перегрузка
  explicit operator int(Foo f) { }

Конструкторы:
  MyClass() { }
  MyClass(int x) : base(x) { }

Свойства:
  int Prop { get { } set { } }        ← полная форма
  int Prop { get => expr; }           ← expression accessor
  int Prop => expr;                   ← expression body property

═══════════════════════════════════════════════════════════════════
ВЫЗОВЫ — всё что ищется в телах
═══════════════════════════════════════════════════════════════════
  Foo()                Direct call
  this.Foo()           Via this
  base.Foo()           Via base
  obj.Foo()            Via object
  Class.Foo()          Static
  obj?.Foo()           Null-conditional
  await Foo()          Async
  Foo<T>()             Generic
  new MyClass()        Constructor
  list.Select(Foo)     Method group (reference without ())
  x => Foo(x)          Lambda body
  delegate { Foo(); }  Anonymous delegate body
"""

import re
import sys
from pathlib import Path
from collections import defaultdict
from dataclasses import dataclass, field


# ══════════════════════════════════════════════════════════════════════════════
# Модель
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class Member:
    kind:  str    # method | constructor | destructor | operator |
                  # property_get | property_set | property_init | property_expr
    name:  str    # короткое имя
    full:  str    # ClassName.name
    owner: str    # класс
    file:  str
    body:  str    # очищенный текст тела
    calls: list = field(default_factory=list)


# ══════════════════════════════════════════════════════════════════════════════
# Очистка: убираем комментарии и строковые литералы
# ══════════════════════════════════════════════════════════════════════════════

def clean(src: str) -> str:
    out = list(src)
    i, n = 0, len(src)

    def blank(a, b):
        for k in range(a, min(b, n)):
            if out[k] != '\n': out[k] = ' '

    while i < n:
        # // однострочный комментарий
        if src[i] == '/' and i+1 < n and src[i+1] == '/':
            end = src.find('\n', i)
            blank(i, end if end != -1 else n)
            i = end if end != -1 else n; continue

        # /* */ блочный комментарий
        if src[i] == '/' and i+1 < n and src[i+1] == '*':
            end = src.find('*/', i+2)
            end = (end+2) if end != -1 else n
            blank(i, end); i = end; continue

        # @"verbatim string"
        if src[i] == '@' and i+1 < n and src[i+1] == '"':
            j = i+2
            while j < n:
                if src[j] == '"':
                    if j+1 < n and src[j+1] == '"': j += 2; continue
                    j += 1; break
                j += 1
            blank(i, j); i = j; continue

        # "обычная строка"
        if src[i] == '"':
            j = i+1
            while j < n:
                if src[j] == '\\': j += 2; continue
                if src[j] == '"':  j += 1; break
                j += 1
            blank(i, j); i = j; continue

        # 'char literal'
        if src[i] == "'":
            j = i+1
            while j < n:
                if src[j] == '\\': j += 2; continue
                if src[j] == "'":  j += 1; break
                j += 1
            blank(i, j); i = j; continue

        i += 1
    return ''.join(out)


# ══════════════════════════════════════════════════════════════════════════════
# Работа со скобками
# ══════════════════════════════════════════════════════════════════════════════

def brace_end(src: str, after: int) -> int:
    """Конец {}-блока. after — позиция ПОСЛЕ открывающей {."""
    depth = 1
    i = after
    n = len(src)
    while i < n:
        if   src[i] == '{': depth += 1
        elif src[i] == '}':
            depth -= 1
            if depth == 0: return i+1
        i += 1
    return n


def arrow_body_end(src: str, after: int) -> int:
    """Конец expression-body после =>. Заканчивается на ; или {."""
    i = after
    n = len(src)
    depth = 0
    while i < n:
        c = src[i]
        if   c in '([': depth += 1
        elif c in ')]': depth -= 1
        elif c == '{' and depth == 0: return i      # начало нового блока
        elif c == ';' and depth == 0: return i+1
        i += 1
    return n


# ══════════════════════════════════════════════════════════════════════════════
# Поиск типов (class/struct/interface/record)
# ══════════════════════════════════════════════════════════════════════════════

_TYPE_DECL_RE = re.compile(
    r'\b(?:class|struct|interface|record(?:\s+struct)?)\s+'
    r'([A-Za-z_]\w*)'        # имя
    r'(?:\s*<[^{>]*>)?'      # <T>
    r'[^{;]*\{',             # до {
    re.MULTILINE
)


def find_types(src: str) -> list:
    """[(name, body_start, body_end)]"""
    result = []
    for m in _TYPE_DECL_RE.finditer(src):
        bs = m.end()
        be = brace_end(src, bs)
        result.append((m.group(1), bs, be))
    return result


def type_at(types: list, pos: int) -> str:
    best_name, best_start = '', -1
    for name, bs, be in types:
        if bs <= pos < be and bs > best_start:
            best_name, best_start = name, bs
    return best_name


# ══════════════════════════════════════════════════════════════════════════════
# Ключевые слова
# ══════════════════════════════════════════════════════════════════════════════

_CTRL = frozenset((
    'if','else','for','foreach','while','do','switch','case','default',
    'try','catch','finally','using','lock','fixed','unsafe','checked',
    'unchecked','goto','return','break','continue','throw','yield',
    'namespace','class','struct','interface','record','enum','delegate',
    'get','set','init','add','remove',
))

_TYPES_KW = frozenset((
    'void','int','uint','long','ulong','short','ushort','byte','sbyte',
    'float','double','decimal','bool','char','string','object','dynamic',
    'var','nint','nuint','Task','ValueTask',
))

_MODS = frozenset((
    'public','private','protected','internal','static','virtual','override',
    'abstract','async','sealed','readonly','extern','new','partial',
    'unsafe','volatile','required',
))

_SKIP_CALL = frozenset((
    'nameof','typeof','sizeof','stackalloc','default',
    'if','while','for','foreach','switch','catch','using','lock',
    'return','new','await','in','out','ref','is','as',
))


# ══════════════════════════════════════════════════════════════════════════════
# Парсинг файла
# ══════════════════════════════════════════════════════════════════════════════

# Паттерн: NAME ( params ) [where ...] [: base/this (...)] { или =>
_FUNC_DECL = re.compile(
    r'\b([A-Za-z_]\w*)\s*'            # имя
    r'(?:<[^>()\[\]]*>)?\s*'          # <T>
    r'\([^)]*\)\s*'                   # (params)
    r'(?:where\s+\w[^{=>]*?)?\s*'    # where T : ...
    r'(?::\s*(?:base|this)\s*\([^)]*\)\s*)?' # : base/this(...)
    r'(?P<open>[{;]|=>)',              # тело
    re.MULTILINE | re.DOTALL
)

# Деструктор: ~Name()
_DTOR_DECL = re.compile(r'~([A-Za-z_]\w*)\s*\(\s*\)\s*\{', re.MULTILINE)

# Оператор: operator X (...)
_OP_DECL = re.compile(
    r'\b(?:explicit\s+|implicit\s+)?operator\s+(\S+)\s*\([^)]*\)\s*(?P<open>[{;]|=>)',
    re.MULTILINE
)

# Свойство { — ищем NAME { (перед именем должен быть тип)
_PROP_DECL = re.compile(r'\b([A-Za-z_]\w*)\s*\{', re.MULTILINE)

# Accessor внутри свойства
_ACCESSOR = re.compile(r'\b(get|set|init)\s*(?:(?P<arr>=>)|\{)')

# Expression-body property: TYPE NAME => expr;
_PROP_EXPR = re.compile(r'\b([A-Za-z_]\w*)\s*=>', re.MULTILINE)


def _prev_word(src: str, pos: int) -> str:
    """Последнее слово перед pos."""
    chunk = src[max(0, pos-120):pos]
    words = re.findall(r'[A-Za-z_]\w*', chunk)
    return words[-1] if words else ''


def _prev_words(src: str, pos: int, n: int = 4) -> list:
    chunk = src[max(0, pos-200):pos]
    return re.findall(r'[A-Za-z_]\w*', chunk)[-n:]


def parse_file(path: Path) -> list:
    src_raw = path.read_text(encoding='utf-8', errors='replace')
    src     = clean(src_raw)
    members = []
    used    = []   # (start, end) занятые диапазоны

    def overlaps(s, e):
        return any(not (e <= a or s >= b) for a, b in used)

    def add(s, e, m: Member):
        used.append((s, e))
        members.append(m)

    types = find_types(src)

    # ── 1. Деструкторы ────────────────────────────────────────────────────
    for m in _DTOR_DECL.finditer(src):
        s = m.start(); bs = m.end(); be = brace_end(src, bs)
        if overlaps(s, be): continue
        owner = type_at(types, s)
        full  = f'{owner}.~{m.group(1)}' if owner else f'~{m.group(1)}'
        add(s, be, Member('destructor', f'~{m.group(1)}', full, owner,
                          path.name, src[bs:be]))

    # ── 2. Операторы ─────────────────────────────────────────────────────
    for m in _OP_DECL.finditer(src):
        if m.group('open') not in ('{', '=>'): continue
        s = m.start()
        if m.group('open') == '{':
            bs = m.end(); be = brace_end(src, bs)
        else:
            bs = m.end(); be = arrow_body_end(src, bs)
        if overlaps(s, be): continue
        owner   = type_at(types, s)
        op_name = f'operator_{re.sub(r"[^A-Za-z0-9]","_",m.group(1))}'
        full    = f'{owner}.{op_name}' if owner else op_name
        add(s, be, Member('operator', op_name, full, owner, path.name, src[bs:be]))

    # ── 3. Свойства { get {} set {} } и expression-body { get => } ───────
    for m in _PROP_DECL.finditer(src):
        pname = m.group(1)
        if pname in _CTRL or pname in _MODS or pname in _TYPES_KW: continue
        prop_s = m.end()           # после {
        prop_e = brace_end(src, prop_s)
        if overlaps(m.start(), prop_e): continue
        # Перед именем должен быть тип (не управляющая конструкция)
        pw = _prev_words(src, m.start())
        if not pw or pw[-1] in _CTRL: continue
        owner = type_at(types, m.start())
        if not owner: continue     # свойства только внутри классов

        # Ищем accessor'ы внутри { }
        found_any = False
        for am in _ACCESSOR.finditer(src, prop_s, prop_e):
            acc = am.group(1)
            if am.group('arr'):
                bs = am.end(); be = arrow_body_end(src, bs)
            else:
                bs = am.end(); be = brace_end(src, bs)
            if overlaps(am.start(), be): continue
            full = f'{owner}.{pname}.{acc}'
            add(am.start(), be, Member(
                f'property_{acc}', f'{pname}.{acc}', full, owner,
                path.name, src[bs:be]
            ))
            found_any = True

        # Если нет accessor'ов — авто-свойство, нет тела
        if not found_any:
            pass  # не добавляем — нечего анализировать

    # ── 4. Expression-body property: TYPE Name => expr; ──────────────────
    for m in _PROP_EXPR.finditer(src):
        pname = m.group(1)
        if pname in _CTRL or pname in _MODS or pname in _TYPES_KW: continue
        s  = m.start()
        bs = m.end()
        be = arrow_body_end(src, bs)
        if overlaps(s, be): continue
        pw = _prev_words(src, s)
        if not pw or pw[-1] in _CTRL: continue
        owner = type_at(types, s)
        if not owner: continue
        full = f'{owner}.{pname}.get'
        add(s, be, Member(
            'property_expr', f'{pname}.get', full, owner, path.name, src[bs:be]
        ))

    # ── 5. Методы и конструкторы ─────────────────────────────────────────
    for m in _FUNC_DECL.finditer(src):
        mname = m.group(1)
        open_ = m.group('open')
        s     = m.start()

        if mname in _CTRL or mname in _MODS: continue

        # Пропускаем abstract/interface (; без тела)
        if open_ == ';': continue

        pw = _prev_words(src, s)
        if not pw or pw[-1] in _CTRL: continue

        if open_ == '{':
            bs = m.end(); be = brace_end(src, bs)
        else:  # =>
            bs = m.end(); be = arrow_body_end(src, bs)

        if overlaps(s, be): continue

        owner = type_at(types, s)
        full  = f'{owner}.{mname}' if owner else mname
        kind  = 'constructor' if (owner and mname == owner) else 'method'

        add(s, be, Member(kind, mname, full, owner, path.name, src[bs:be]))

    return members


# ══════════════════════════════════════════════════════════════════════════════
# Поиск вызовов в теле
# ══════════════════════════════════════════════════════════════════════════════

# Паттерны вызовов:
# 1. A.B.C(  — цепочка
# 2. Name(   — прямой
# 3. new Name( — конструктор
# 4. Name?.Method( — null-conditional
# 5. await Name(
# 6. Name<T>( — generic

_CHAIN_CALL = re.compile(
    r'\b([A-Za-z_]\w*(?:\.[A-Za-z_]\w*)+)\s*'
    r'(?:<[^>()]*>)?\s*'
    r'(?:\?\.)?'
    r'\s*\('
)

_SIMPLE_CALL = re.compile(
    r'(?:^|(?<=[^\w.]))'          # начало или не после слова/точки
    r'(?:new\s+|await\s+)?'
    r'\b([A-Za-z_]\w*)\s*'
    r'(?:<[^>()]*>)?\s*'
    r'(?:\?\.)?'
    r'\s*\(',
    re.MULTILINE
)

_NULL_COND = re.compile(
    r'\b([A-Za-z_]\w*)\s*\?\.\s*([A-Za-z_]\w*)\s*\('
)


def find_calls(body: str) -> set:
    calls = set()

    # Цепочки A.B.C(
    for m in _CHAIN_CALL.finditer(body):
        chain = m.group(1)
        calls.add(chain)
        for part in chain.split('.'):
            if part and part not in _SKIP_CALL:
                calls.add(part)

    # Null-conditional obj?.Method(
    for m in _NULL_COND.finditer(body):
        if m.group(2) not in _SKIP_CALL:
            calls.add(m.group(2))
        if m.group(1) not in _SKIP_CALL:
            calls.add(m.group(1))

    # Простые вызовы Name(
    for m in _SIMPLE_CALL.finditer(body):
        name = m.group(1)
        if name and name not in _SKIP_CALL:
            calls.add(name)

    return calls


# ══════════════════════════════════════════════════════════════════════════════
# Граф вызовов
# ══════════════════════════════════════════════════════════════════════════════

def build_graph(all_members: list):
    by_full  = {}
    by_short = defaultdict(list)

    for m in all_members:
        by_full[m.full] = m
        by_short[m.name].append(m)
        # Последняя часть full (напр. "get" из "Class.Prop.get")
        last = m.full.split('.')[-1]
        if last not in by_short or m not in by_short[last]:
            by_short[last].append(m)

    for mem in all_members:
        raw      = find_calls(mem.body)
        resolved = set()

        for call in raw:
            # 1. Точное совпадение по full
            if call in by_full:
                t = by_full[call]
                if t.full != mem.full:
                    resolved.add(t.full)
                continue

            # 2. По короткому имени
            if call in by_short:
                for t in by_short[call]:
                    if t.full == mem.full: continue
                    # Тот же класс — приоритет
                    if t.owner == mem.owner:
                        resolved.add(t.full)
                    elif len(by_short[call]) == 1:
                        resolved.add(t.full)

        mem.calls = sorted(resolved)


# ══════════════════════════════════════════════════════════════════════════════
# PlantUML
# ══════════════════════════════════════════════════════════════════════════════

_FILE_COLORS = [
    'D5F5E3','D6EAF8','FDEBD0','F5EEF8','EBF5FB',
    'FEF9E7','E8F8F5','FDEDEC','EAF2FF','D1F2EB',
]

_KIND_ICON = {
    'method':        '+',
    'constructor':   '«new»',
    'destructor':    '~',
    'operator':      '«op»',
    'property_get':  '⊙get',
    'property_set':  '⊙set',
    'property_init': '⊙init',
    'property_expr': '⊙get',
}


def _pid(s: str) -> str:
    return re.sub(r'[^A-Za-z0-9]', '_', s).strip('_') or 'x'


def generate_puml(files_members: dict) -> str:
    lines = []
    w = lines.append

    w('@startuml')
    w('left to right direction')
    w('skinparam linetype ortho')
    w('skinparam nodesep 30')
    w('skinparam ranksep 60')
    w('skinparam packageStyle frame')
    w('skinparam shadowing false')
    w('skinparam padding 6')
    w('skinparam ArrowColor #4A90D9')
    w('skinparam ArrowThickness 1.5')
    w('skinparam package {')
    w('  BorderColor #7F8C8D')
    w('  FontSize 11')
    w('  FontStyle bold')
    w('  BackgroundColor #FAFAFA')
    w('}')
    w('skinparam rectangle {')
    w('  FontName Consolas,monospace')
    w('  FontSize 10')
    w('  BorderColor #95A5A6')
    w('}')
    w('')

    id_map = {}
    fi = 0

    for filename, members in files_members.items():
        visible = [m for m in members if '.' in m.full]
        if not visible: continue
        color = _FILE_COLORS[fi % len(_FILE_COLORS)]; fi += 1
        fid   = _pid(filename)
        w(f'package "{Path(filename).stem}  [C#]" {{')

        by_owner = defaultdict(list)
        for m in visible:
            by_owner[m.owner].append(m)

        for owner in sorted(by_owner):
            w(f'  package "{owner}" {{')
            w('')
            for m in by_owner[owner]:
                nid   = _pid(f'{fid}__{m.full}')
                id_map[m.full] = nid
                icon  = _KIND_ICON.get(m.kind, '+')
                label = f'{icon} {m.name}()'
                w(f'    rectangle "  {label}  " as {nid} #{color}')
            w('')
            w('  }')

        w('}')
        w('')

    w("' ── вызовы ──────────────────────────────────────────────────────────")
    drawn = set()
    for members in files_members.values():
        for m in members:
            src_id = id_map.get(m.full)
            if not src_id: continue
            for callee in m.calls:
                dst_id = id_map.get(callee)
                if not dst_id or dst_id == src_id: continue
                e = (src_id, dst_id)
                if e not in drawn:
                    drawn.add(e)
                    w(f'{src_id} --> {dst_id}')

    w('')
    w('legend right')
    w('  + method  |  «new» constructor  |  ~ destructor')
    w('  «op» operator  |  ⊙ property accessor')
    w('  --> calls')
    w('endlegend')
    w('@enduml')

    return '\n'.join(lines)


# ══════════════════════════════════════════════════════════════════════════════
# Статистика
# ══════════════════════════════════════════════════════════════════════════════

def print_stats(all_members, files_members):
    by_kind = defaultdict(int)
    for m in all_members: by_kind[m.kind] += 1
    total_calls = sum(len(m.calls) for m in all_members)

    print(f'\nФайлов   : {len(files_members)}')
    print(f'Членов   : {len(all_members)}')
    for k, v in sorted(by_kind.items()):
        print(f'  {k:<20}: {v}')
    print(f'Связей   : {total_calls}')

    callers = sorted(all_members, key=lambda m: -len(m.calls))
    if callers and callers[0].calls:
        print('\nТоп вызывающих:')
        for m in callers[:10]:
            if not m.calls: break
            print(f'  {len(m.calls):>3}  {m.full:<55} [{m.file}]')

    callee_cnt = defaultdict(int)
    for m in all_members:
        for c in m.calls: callee_cnt[c] += 1
    if callee_cnt:
        print('\nСамые вызываемые:')
        for name, cnt in sorted(callee_cnt.items(), key=lambda x: -x[1])[:10]:
            print(f'  {cnt:>3}  {name}')
    print()


# ══════════════════════════════════════════════════════════════════════════════
# Интерактивный выбор файлов
# ══════════════════════════════════════════════════════════════════════════════

def interactive_pick(all_files: list) -> list:
    print('\nНайденные файлы:')
    for i, p in enumerate(all_files, 1):
        print(f'  [{i:>3}] {p.name}')

    print()
    print('Выбор:')
    print('  Enter / "a"    — все файлы')
    print('  1 3 5          — по номерам (через пробел)')
    print('  1-5            — диапазон')
    print('  1,3,7-10       — комбинация')
    print()

    raw = input('> ').strip()
    if not raw or raw.lower() == 'a':
        return all_files

    selected = []
    seen     = set()

    for tok in re.split(r'[,\s]+', raw):
        tok = tok.strip()
        if not tok:
            continue
        m = re.fullmatch(r'(\d+)-(\d+)', tok)
        if m:
            for idx in range(int(m.group(1)), int(m.group(2)) + 1):
                if 1 <= idx <= len(all_files) and idx not in seen:
                    selected.append(all_files[idx - 1])
                    seen.add(idx)
        elif tok.isdigit():
            idx = int(tok)
            if 1 <= idx <= len(all_files) and idx not in seen:
                selected.append(all_files[idx - 1])
                seen.add(idx)
        else:
            print(f'  ! Непонятный токен: {tok!r} — пропущен')

    if not selected:
        print('Ничего не выбрано, берём все файлы.')
        return all_files
    return selected


# ══════════════════════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════════════════════

EXCLUDE = {'.git','obj','bin','node_modules','__pycache__',
           'x64','x86','Debug','Release'}


def main():
    HERE = Path(__file__).resolve().parent

    all_files = sorted(
        p for p in HERE.rglob('*.cs')
        if not any(ex in p.parts for ex in EXCLUDE)
    )

    if not all_files:
        print(f'Нет .cs файлов в {HERE}')
        input('Enter...'); return

    print(f'Корень : {HERE}')
    print(f'Файлов : {len(all_files)}')

    # ── Выбор файлов (аргументы командной строки или интерактивно) ────────
    if len(sys.argv) > 1:
        chosen = []
        for arg in sys.argv[1:]:
            ap = Path(arg)
            if not ap.is_absolute():
                ap = HERE / ap
            if ap.is_dir():
                found = sorted(
                    p for p in ap.rglob('*.cs')
                    if not any(ex in p.parts for ex in EXCLUDE)
                )
                chosen.extend(found)
                print(f'  Папка {arg}: {len(found)} файлов')
            elif ap.is_file() and ap.suffix.lower() == '.cs':
                chosen.append(ap)
                print(f'  Файл: {ap.name}')
            else:
                print(f'  ! Не найдено / не поддерживается: {arg}')
        if not chosen:
            print('Ни одного файла по аргументам.')
            input('Enter...'); return
    else:
        chosen = interactive_pick(all_files)

    # Дедупликация
    seen_r = set(); unique = []
    for p in chosen:
        rp = p.resolve()
        if rp not in seen_r:
            seen_r.add(rp); unique.append(p)
    chosen = unique

    print(f'\nОбрабатываю {len(chosen)} файл(ов):\n')

    files_members = {}
    all_members   = []

    for p in chosen:
        try:
            mems = parse_file(p)
            files_members[p.name] = mems
            all_members.extend(mems)
            print(f'  OK  {p.name:<45} {len(mems)} членов')
        except Exception as e:
            import traceback
            print(f'  ERR {p.name}: {e}')
            traceback.print_exc()

    print('\nСтрою граф...')
    build_graph(all_members)
    print_stats(all_members, files_members)

    out = HERE / 'map.puml'
    out.write_text(generate_puml(files_members), encoding='utf-8')
    print(f'Записано : {out}')
    print('Открыть  : https://www.plantuml.com/plantuml/uml/')
    input('\nEnter для выхода...')


if __name__ == '__main__':
    main()
