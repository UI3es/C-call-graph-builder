cs_callgraph.py  —  C# call graph builder → [planttext](https://www.planttext.com/)

Положи рядом с .cs файлами. Запусти через PyCharm (Run / F5).
Результат: map.puml рядом со скриптом.

═══════════════════════════════════════════════════════════════════
ОБЪЯВЛЕНИЯ — всё что парсится
═══════════════════════════════════════════════════════════════════
Методы:
```
  void Foo() { }
  public static int Bar(int x) { }
  async Task Baz() { }
  int Qux() => expr;                   ← expression body
  T Generic<T>() where T : class { }
  ~MyClass() { }                       ← деструктор
  operator +(A a, B b) { }            ← перегрузка
  explicit operator int(Foo f) { }
```
```
Конструкторы:
  MyClass() { }
  MyClass(int x) : base(x) { }
```
```
Свойства:
  int Prop { get { } set { } }        ← полная форма
  int Prop { get => expr; }           ← expression accessor
  int Prop => expr;                   ← expression body property
```
═══════════════════════════════════════════════════════════════════
ВЫЗОВЫ — всё что ищется в телах
═══════════════════════════════════════════════════════════════════
```
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
```
Привет вывода: <img width="1066" height="2096" alt="image" src="https://github.com/user-attachments/assets/8a4697ea-bdba-4bc0-a9a4-56ccc1b517fb" />
