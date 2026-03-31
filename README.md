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
Привет вывода: https://uml.planttext.com/plantuml/svg/rPYzRXD14CTxItw7KL802aI9m25f48u_GWe-7KI1aBNSZUrJrhl7tbf9W21gQ6bu1ZeQ2YIAF45uXJm9ktSNtrtkQpTn2XJBbkVs_vlPsO-P-64WYP2pAMqsA8uaI0x26qyak9v0HtgSDHl1liTy8iWKgCTG7la8NCW9JpzXtCK0VRYxbhOAmlQrTIDZzOcpJyOua4SKOQGic7uQJ8ZB3pmsXX6X0MQ5hgiVRAIDRI7uGOTJBc3vNdjhhRkLUxetyPnzXa40wwkjWaZWGxC1iCs5Yo8ctUzlTZQxsjpdJ0wyzmZhw_ElOUHlENL3dOAC1PynDzRss_glsJZEf49bax0nZPrfp1CrS-Xm5d1AWjjJpdYW0iAiqxLSQ5kjTgkz4UARZVCPB0aSqMZ105vtbjyiHNxcpryoJnwrVMy76GeYkGW7w26GYcq9uEpBzp5Ay5VL-yrRe4maW8G-T8BXC0SR-aCjMkws-gtUtOXxV374vpCI435Gwr0QPMP8JOGgSn8FPIREZ3uCDMk9DN6m6xrsVxF0mGhigWbwXAeLC4OdaahoO3AJQdypO-wv8A4M9hSZa4XynGLrUwwdbgGumRbXDKaUJaWGZiwaEKS9uyvRv-eeuVrkRxkxLh6Yyl1IRfIkni4AFFMHMOErg9hATbxkscErgeORgIw1Zcmrz1VgihRFSwohONUHugKYZuILzC647_JKbIwiyNDbmgyxHxKdgFrij-puhC0BV3TJDRGeq8iXAium7gwYQ_Lw9NT7-Pue8iutGXsmB_XqMzUlm0wTw2gT353k2CzLMuVJcIuXfbvomZetUnv5TSEFlB65YqHKYTz1QPUZkQ0IMteGY_T8TFhASULdhuWtFt2LMUqGIj-gtMyyyxGcWSUdBNMIzb08uh77XAclfOMei1XVZ22BojJYYiaz8inLYn-oN5DsHcI0Zv9iYOz51dYzVSjNfX0UIWpk1JtEb9meSYiUtgytuEpRP_M2qvz_lvx-ElsZFsFR__9gDcpQopjt7bZqZCs6NVEWwROzmVNwYBRizVe8Bq0R5t4DlE2blAHT3pjNoAxDJLBChkx2h9rQq5HABt0RVbGV3J9blOyAoOjFK5oG3MPWVzgAsPUOGqMlQPJwiCyr9APQp0MoyutbOk6fbdA1uAIXN23KuiYO0Ssti4L2atRoAjpo9j7iSfr7KOlEzeW6zrtIFkbcYU8OcHlz4AkRg1MOefnmzG_fHu2J7mmFJdw3mraWnSm9V-fHza_Wuhb1Yqv-S5yDutxq2rquvkpBT_25DiaZ88wZsf1ei0xHKTDJKqCTklRVR3nKxxCf_GS0
