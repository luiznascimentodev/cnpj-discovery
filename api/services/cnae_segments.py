_SEGMENT_DIVISIONS: list[tuple[str, set[int]]] = [
    ("Tecnologia e TI", {62, 63}),
    ("Alimentação e Bebidas", {10, 11, 56}),
    ("Comércio Varejista", {47}),
    ("Comércio Atacadista", {46}),
    ("Construção Civil", {41, 42, 43}),
    ("Saúde e Bem-estar", {75, 86, 87, 88, 96}),
    ("Educação", {85}),
    ("Serviços Financeiros", {64, 65, 66}),
    ("Transporte e Logística", {49, 50, 51, 52, 53}),
    ("Indústria", {13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 32, 33}),
    ("Agropecuária", {1, 2, 3}),
    ("Serviços Profissionais", {69, 70, 71, 72, 73, 74}),
    ("Imóveis", {68}),
]

_SEGMENT_ORDER = [label for label, _ in _SEGMENT_DIVISIONS] + ["Outros"]


def _division(code: int) -> int:
    return code // 100000


def classify_cnae(code: int) -> str:
    div = _division(code)
    for label, divisions in _SEGMENT_DIVISIONS:
        if div in divisions:
            return label
    return "Outros"


def group_cnaes(cnaes: list[dict]) -> list[dict]:
    if not cnaes:
        return []
    groups: dict[str, list] = {}
    for cnae in cnaes:
        label = classify_cnae(cnae["codigo"])
        groups.setdefault(label, []).append(cnae)
    return [
        {"label": label, "cnaes": groups[label]}
        for label in _SEGMENT_ORDER
        if label in groups
    ]
