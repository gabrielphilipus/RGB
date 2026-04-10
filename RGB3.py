import math
import tkinter as tk
from tkinter import simpledialog, messagebox, colorchooser
from PIL import Image, ImageTk, ImageDraw
import pyautogui
import time
import colorsys
import json
import os
import struct
import numpy as np
from datetime import datetime

try:
    from sklearn.cluster import KMeans
    SKLEARN_AVAILABLE = True
except ImportError:
    SKLEARN_AVAILABLE = False

def hex_to_rgb(hex_code):
    hex_code = hex_code.lstrip('#')
    return [int(hex_code[i:i+2], 16) for i in (0, 2, 4)]

def luminancia(rgb):
    """Calcula luminância relada (0-1) para determinar contraste"""
    r, g, b = [x / 255.0 for x in rgb]
    return 0.2126 * r + 0.7152 * g + 0.0722 * b

def cor_texto_contraste(hex_cor):
    """Retorna preto ou branco dependendo do contraste com a cor de fundo"""
    rgb = hex_to_rgb(hex_cor)
    lum = luminancia(rgb)
    return "#000000" if lum > 0.5 else "#ffffff"

def rgb_to_hex(rgb):
    r, g, b = [max(0, min(255, int(v))) for v in rgb]
    return '#{:02x}{:02x}{:02x}'.format(r, g, b)

def rgb_to_xyz(rgb):
    res = []
    for c in rgb:
        v = c / 255.0
        v = pow((v + 0.055) / 1.055, 2.4) if v > 0.04045 else v / 12.92
        res.append(v * 100)
    return (res[0] * 0.4124 + res[1] * 0.3576 + res[2] * 0.1805,
            res[0] * 0.2126 + res[1] * 0.7152 + res[2] * 0.0722,
            res[0] * 0.0193 + res[1] * 0.1192 + res[2] * 0.9505)

def xyz_to_lab(xyz):
    ref = (95.047, 100.000, 108.883)
    res = [pow(v/r, 1/3) if v/r > 0.008856 else (7.787*(v/r))+(16/116) for v, r in zip(xyz, ref)]
    return ((116 * res[1]) - 16, 500 * (res[0] - res[1]), 200 * (res[1] - res[2]))

def lab_to_xyz(lab):
    y = (lab[0] + 16) / 116
    x, z = lab[1]/500 + y, y - lab[2]/200
    res = [pow(v, 3) if v**3 > 0.008856 else (v - 16/116)/7.787 for v in [x, y, z]]
    ref = (95.047, 100.000, 108.883)
    return (res[0]*ref[0], res[1]*ref[1], res[2]*ref[2])

def xyz_to_rgb(xyz):
    x, y, z = [v / 100 for v in xyz]
    r, g, b = x*3.2406 + y*-1.5372 + z*-0.4986, x*-0.9689 + y*1.8758 + z*0.0415, x*0.0557 + y*-0.2040 + z*1.0570
    res = [max(0, min(1, v)) for v in [r, g, b]]
    res = [1.055 * pow(v, 1/2.4) - 0.055 if v > 0.0031308 else 12.92 * v for v in res]
    return [max(0, min(255, v * 255)) for v in res]

def delta_e_cie76(l1, l2):
    return math.sqrt(sum((a-b)**2 for a, b in zip(l1, l2)))

# ── WCAG 2.1 ────────────────────────────────────────────────────────────────

def luminancia_relativa(hex_cor):
    """Luminância relativa WCAG 2.1 (0–1) conforme IEC 61966-2-1."""
    rgb = hex_to_rgb(hex_cor)
    canais = []
    for c in rgb:
        v = c / 255.0
        canais.append(v / 12.92 if v <= 0.03928 else pow((v + 0.055) / 1.055, 2.4))
    return 0.2126 * canais[0] + 0.7152 * canais[1] + 0.0722 * canais[2]

def razao_contraste(hex_a, hex_b):
    """Razão de contraste WCAG entre duas cores (1:1 a 21:1)."""
    la = luminancia_relativa(hex_a)
    lb = luminancia_relativa(hex_b)
    lighter, darker = max(la, lb), min(la, lb)
    return (lighter + 0.05) / (darker + 0.05)

def nivel_wcag(razao, tamanho="normal"):
    """
    Retorna o nível WCAG atingido para texto sobre fundo.
    tamanho: 'normal'  → limites 4.5 (AA) e 7.0 (AAA)
             'grande'  → limites 3.0 (AA) e 4.5 (AAA)  [≥18pt ou ≥14pt bold]
             'ui'      → limite  3.0 (AA) apenas         [componentes de UI]
    Retorna: 'AAA', 'AA', 'AA-grande' (passa só para texto grande) ou 'Falha'.
    """
    if tamanho == "normal":
        if razao >= 7.0:  return "AAA"
        if razao >= 4.5:  return "AA"
        return "Falha"
    elif tamanho == "grande":
        if razao >= 4.5:  return "AAA"
        if razao >= 3.0:  return "AA"
        return "Falha"
    else:  # ui
        return "AA" if razao >= 3.0 else "Falha"

# Cores fixas dos badges — independentes do tema, para máxima legibilidade
_WCAG_CORES = {
    "AAA":       {"bg": "#1b5e20", "fg": "#ffffff"},
    "AA":        {"bg": "#1565c0", "fg": "#ffffff"},
    "AA-grande": {"bg": "#e65100", "fg": "#ffffff"},
    "Falha":     {"bg": "#b71c1c", "fg": "#ffffff"},
}

def kelvin_to_rgb(kelvin):
    temp = kelvin / 100
    if temp <= 66:
        r = 255
        g = max(0, min(255, 99.47 * math.log(temp) - 161.12))
        b = 0 if temp <= 19 else max(0, min(255, 138.52 * math.log(temp - 10) - 305.04))
    else:
        r = max(0, min(255, 329.70 * pow(temp - 60, -0.1332)))
        g = max(0, min(255, 288.12 * pow(temp - 60, -0.0755)))
        b = 255
    return (r/255, g/255, b/255)

# ── ESPAÇO LCH (Lightness · Chroma · Hue) ──────────────────────────────────
# Derivado do LAB, mas com coordenadas cilíndricas (ângulo de matiz + raio).
# Rotacionar o matiz em LCH é perceptualmente uniforme — ao contrário do HSL,
# a luminosidade e o croma percebidos permanecem constantes entre as cores geradas.

def lab_to_lch(lab):
    """Converte LAB → LCH. Retorna (L, C, H°)."""
    L, a, b = lab
    C = math.sqrt(a**2 + b**2)
    H = math.degrees(math.atan2(b, a)) % 360
    return (L, C, H)

def lch_to_lab(lch):
    """Converte LCH → LAB."""
    L, C, H = lch
    h_rad = math.radians(H)
    return (L, C * math.cos(h_rad), C * math.sin(h_rad))

def lch_para_hex(lch):
    """Converte LCH diretamente para HEX (passando por LAB → XYZ → RGB)."""
    return rgb_to_hex(xyz_to_rgb(lab_to_xyz(lch_to_lab(lch))))

def hex_para_lch(hex_cor):
    """Converte HEX diretamente para LCH."""
    return lab_to_lch(xyz_to_lab(rgb_to_xyz(hex_to_rgb(hex_cor))))

def girar_matiz(lch, delta_graus):
    """Rotaciona o matiz de um LCH em delta_graus, preservando L e C."""
    L, C, H = lch
    return (L, C, (H + delta_graus) % 360)

# ── GERADORES DE PALETAS HARMÔNICAS ─────────────────────────────────────────

def paleta_complementar(hex_base):
    """Cor base + complementar (180°). 2 cores."""
    lch = hex_para_lch(hex_base)
    return [hex_base, lch_para_hex(girar_matiz(lch, 180))]

def paleta_split_complementar(hex_base):
    """Base + os dois vizinhos do complementar (±150°). 3 cores."""
    lch = hex_para_lch(hex_base)
    return [hex_base,
            lch_para_hex(girar_matiz(lch, 150)),
            lch_para_hex(girar_matiz(lch, 210))]

def paleta_analogica(hex_base, passos=2, angulo=30):
    """Base + N vizinhos em cada lado em espaçamento angular uniforme."""
    lch = hex_para_lch(hex_base)
    cores = []
    for i in range(-passos, passos + 1):
        cores.append(lch_para_hex(girar_matiz(lch, i * angulo)))
    return cores

def paleta_triade(hex_base):
    """3 cores equidistantes (0°, 120°, 240°)."""
    lch = hex_para_lch(hex_base)
    return [lch_para_hex(girar_matiz(lch, d)) for d in (0, 120, 240)]

def paleta_tetrade(hex_base):
    """4 cores em quadrado cromático (0°, 90°, 180°, 270°)."""
    lch = hex_para_lch(hex_base)
    return [lch_para_hex(girar_matiz(lch, d)) for d in (0, 90, 180, 270)]

def paleta_pentade(hex_base):
    """5 cores equidistantes (0°, 72°, 144°, 216°, 288°)."""
    lch = hex_para_lch(hex_base)
    return [lch_para_hex(girar_matiz(lch, d)) for d in (0, 72, 144, 216, 288)]

def paleta_monocromatica(hex_base, num=6):
    """Variações de luminosidade e croma mantendo o mesmo matiz LCH."""
    lch = hex_para_lch(hex_base)
    L_base, C_base, H = lch
    cores = []
    # Distribui L de 20 a 85 para evitar branco/preto puros
    for i in range(num):
        t = i / (num - 1)
        L_novo = 20 + t * 65
        # Reduz ligeiramente o croma nas extremidades para parecer natural
        fator_c = 1.0 - 0.35 * abs(t - 0.5) * 2
        C_novo = max(0, C_base * fator_c)
        cores.append(lch_para_hex((L_novo, C_novo, H)))
    return cores

def paleta_dupla_complementar(hex_base, angulo_split=30):
    """Dois pares complementares com offset angular (0°, angulo°, 180°, 180°+angulo°). 4 cores."""
    lch = hex_para_lch(hex_base)
    return [lch_para_hex(girar_matiz(lch, d))
            for d in (0, angulo_split, 180, 180 + angulo_split)]

# Catálogo público — usado pela UI para popular o menu
HARMONIAS = {
    "Complementar":         {"fn": paleta_complementar,       "desc": "Opostos no círculo cromático"},
    "Split-Complementar":   {"fn": paleta_split_complementar, "desc": "Base + vizinhos do complementar"},
    "Análoga":              {"fn": paleta_analogica,           "desc": "Vizinhos em 30° de cada lado"},
    "Tríade":               {"fn": paleta_triade,              "desc": "Três cores equidistantes (120°)"},
    "Tétrade":              {"fn": paleta_tetrade,             "desc": "Quadrado cromático (90°)"},
    "Pêntade":              {"fn": paleta_pentade,             "desc": "Cinco cores equidistantes (72°)"},
    "Monocromática":        {"fn": paleta_monocromatica,       "desc": "Variações de luminosidade e croma"},
    "Dupla Complementar":   {"fn": paleta_dupla_complementar,  "desc": "Dois pares complementares"},
}

def simular_daltonismo(rgb_linear, tipo):
    rl, gl, bl = rgb_linear
    if tipo == "deuteranopia": return [0.625*rl + 0.375*gl, 0.7*rl + 0.3*gl, 0.3*gl + 0.7*bl]
    if tipo == "protanopia": return [0.567*rl + 0.433*gl, 0.558*rl + 0.442*gl, 0.242*gl + 0.758*bl]
    if tipo == "tritanopia": return [0.95*rl + 0.05*gl, 0.433*gl + 0.567*bl, 0.475*gl + 0.525*bl]
    if tipo == "acromatopsia":
        lum = 0.2126*rl + 0.7152*gl + 0.0722*bl
        return [lum, lum, lum]
    return rgb_linear

#CLASSE PRINCIPAL

class AppCores:
    def __init__(self, root):
        self.root = root
        self.root.title("Color Lab Pro")
        self.root.geometry("850x600")
        self.root.attributes("-topmost", True)
        
        # Variáveis de Controle
        self.cores_hex = []
        self.cor_atual = "#0078d7"
        self.passo_delta = tk.DoubleVar(value=1.5)
        self.tema = tk.StringVar(value="claro")
        self.sim_daltonismo = tk.StringVar(value="normal")
        self.config_win = None
        self.historico_cores = []  # Últimas 10 cores usadas
        self.mostrar_preview_contraste = tk.BooleanVar(value=True)  # Controle do preview "Aa"
        self.mostrar_wcag = tk.BooleanVar(value=True)               # Badge WCAG no canvas
        self.wcag_fundo_var = tk.StringVar(value="preto_branco")    # Fundo de referência WCAG
        self.ultima_atividade = ""  # Memória da última atividade realizada

        self.mixer_color_a = None
        self.mixer_color_b = "#ffffff"

        # Projetos/Paletas salvas
        self.arquivo_projetos = "projetos.json"
        self.projetos = {}  # {nome: {cores_hex, cor_atual, data_criacao, data_modificacao}}
        self.projeto_atual = None  # Nome do projeto atualmente carregado
        self.frame_projetos = None  # Frame do painel lateral

        # Pilha de estados para Undo/Redo
        self._undo_stack = []  # Pilha de estados para desfazer
        self._redo_stack = []  # Pilha de estados para refazer
        self._max_undo_states = 50  # Limite de estados na pilha
        self._salvando_estado = False  # Flag para evitar salvamento recursivo
        
        # Ajustes de Imagem
        self.adj_bright = tk.DoubleVar(value=0)
        self.adj_contrast = tk.DoubleVar(value=1.0)
        self.adj_gamma = tk.DoubleVar(value=1.0)
        self.adj_sat = tk.DoubleVar(value=1.0)
        self.adj_hue = tk.DoubleVar(value=0)
        self.adj_temp = tk.DoubleVar(value=6500)

        # Debounce timer para sliders
        self._debounce_timer = None
        self._debounce_delay = 100  # ms

        self.arquivo_config = "config.json"
        self.paletas = {
            "claro": { "window_bg": "#ffffff", "text_fg": "#000000", "btn": "#e1e1e1", "special": "#e3f2fd", "canvas": "#f0f0f0" },
            "escuro": { "window_bg": "#1e1e1e", "text_fg": "#ffffff", "btn": "#333333", "special": "#2196f3", "canvas": "#121212" }
        }

        self.carregar_configuracoes()
        self.carregar_projetos()

        self.frame_menu = tk.Frame(self.root, pady=15)
        self.frame_menu.pack(side=tk.TOP, fill=tk.X)

        tk.Button(self.frame_menu, text="⌨️ HEX", command=self.ferramenta_digitar, width=12).pack(side=tk.LEFT, padx=10)
        tk.Button(self.frame_menu, text="🎨 Seletor", command=self.ferramenta_seletor, width=12).pack(side=tk.LEFT, padx=10)
        self.btn_gotas = tk.Button(self.frame_menu, text="🧪 Conta-Gotas", command=self.ferramenta_conta_gotas, width=12)
        self.btn_gotas.pack(side=tk.LEFT, padx=10)
        tk.Button(self.frame_menu, text="🎡 Harmonias", command=self.abrir_harmonias, width=12).pack(side=tk.LEFT, padx=10)
        tk.Button(self.frame_menu, text="🧬 Mixer", command=self.abrir_mixer, width=10).pack(side=tk.LEFT, padx=10)
        tk.Button(self.frame_menu, text="📷 Importar", command=self.importar_imagem, width=12).pack(side=tk.LEFT, padx=10)
        tk.Button(self.frame_menu, text="💾 Exportar", command=self.exportar_paleta, width=12).pack(side=tk.LEFT, padx=10)
        # Botões de Projetos
        tk.Button(self.frame_menu, text="💼 Salvar Projeto", command=self.abrir_salvar_projeto, width=14).pack(side=tk.LEFT, padx=10)
        tk.Button(self.frame_menu, text="📂 Projetos", command=self.abrir_gerenciar_projetos, width=12).pack(side=tk.LEFT, padx=10)
        # Undo/Redo buttons
        tk.Button(self.frame_menu, text="↩️ Undo", command=self.undo, width=10).pack(side=tk.RIGHT, padx=5)
        tk.Button(self.frame_menu, text="↪️ Redo", command=self.redo, width=10).pack(side=tk.RIGHT, padx=5)
        tk.Button(self.frame_menu, text="⚙️ Config", command=self.abrir_configuracoes, width=12).pack(side=tk.RIGHT, padx=10)

        self.label_info = tk.Label(self.root, text=f"Color Lab Pro v4.6 | Base: {self.cor_atual}")
        self.label_info.pack()

        # Container principal: projetos + canvas + histórico
        self.frame_principal = tk.Frame(self.root)
        self.frame_principal.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)

        # Painel lateral de projetos
        self.frame_projetos = tk.Frame(self.frame_principal, width=180)
        self.frame_projetos.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 10))
        self.frame_projetos.pack_propagate(False)

        # Painel central (canvas)
        self.frame_canvas = tk.Frame(self.frame_principal)
        self.frame_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.canvas = tk.Canvas(self.frame_canvas, highlightthickness=0)
        self.canvas.pack(fill=tk.BOTH, expand=True)

        # Painel de histórico
        self.frame_historico = tk.Frame(self.frame_principal, width=60)
        self.frame_historico.pack(side=tk.RIGHT, fill=tk.Y, padx=(10, 0))

        self.canvas.bind("<Configure>", lambda e: self.desenhar_gradiente())
        self.canvas.bind("<Button-1>", self.copiar_clique)

        # Atalhos Undo/Redo (Ctrl+Z / Ctrl+Y)
        self.root.bind("<Control-z>", self.undo)
        self.root.bind("<Control-y>", self.redo)
        # Alternativa: Ctrl+Shift+Z também funciona como redo
        self.root.bind("<Control-Shift-Z>", self.redo)
        # Atalho Ctrl+S para salvar projeto rápido
        self.root.bind("<Control-s>", self.salvar_projeto_rapido)

        self.root.protocol("WM_DELETE_WINDOW", self.ao_fechar)
        self.aplicar_tema()

        # Cria a UI do painel de projetos
        self.criar_ui_painel_projetos()

        # Salva o estado inicial vazio
        self.salvar_estado("Inicialização")
        self.gerar_lista_cores(self.cor_atual)

        # Mostra mensagem de boas-vindas com memória da última atividade
        self.mostrar_memoria_inicial()

    # SISTEMA DE PROJETOS/PALETAS SALVAS
    def carregar_projetos(self):
        """Carrega projetos salvos do arquivo projetos.json"""
        if os.path.exists(self.arquivo_projetos):
            try:
                with open(self.arquivo_projetos, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.projetos = data.get("projetos", {})
            except Exception as e:
                print(f"Erro ao carregar projetos: {e}")
                self.projetos = {}

    def salvar_projetos(self):
        """Salva projetos no arquivo projetos.json"""
        try:
            data = {
                "projetos": self.projetos,
                "ultima_atualizacao": datetime.now().isoformat()
            }
            with open(self.arquivo_projetos, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"Erro ao salvar projetos: {e}")

    def criar_ui_painel_projetos(self):
        """Cria a UI do painel lateral de projetos com scrollbar"""
        for w in self.frame_projetos.winfo_children():
            w.destroy()

        p = self.paletas[self.tema.get()]
        self.frame_projetos.config(bg=p["window_bg"])

        # Título
        tk.Label(
            self.frame_projetos,
            text="📂 Projetos",
            bg=p["window_bg"],
            fg=p["text_fg"],
            font=("Arial", 11, "bold")
        ).pack(pady=(10, 5))

        # Botão Novo Projeto
        tk.Button(
            self.frame_projetos,
            text="➕ Novo Projeto",
            command=self.criar_novo_projeto,
            bg=p["special"],
            fg="#ffffff",
            relief=tk.FLAT,
            width=18,
            font=("Arial", 9, "bold")
        ).pack(pady=(0, 8))

        # Botão Gerenciar
        tk.Button(
            self.frame_projetos,
            text="⚙️ Gerenciar",
            command=self.abrir_gerenciar_projetos,
            bg=p["btn"],
            fg=p["text_fg"],
            relief=tk.FLAT,
            width=18
        ).pack(pady=(0, 8))

        # Separador
        tk.Frame(self.frame_projetos, height=2, bg=p["btn"]).pack(fill=tk.X, padx=10, pady=5)

        # Label para projetos recentes
        tk.Label(
            self.frame_projetos,
            text="Recentes:",
            bg=p["window_bg"],
            fg=p["text_fg"],
            font=("Arial", 9, "bold"),
            anchor=tk.W
        ).pack(fill=tk.X, padx=10, pady=(5, 0))

        # Container com scrollbar para lista de projetos
        self.container_projetos = tk.Frame(self.frame_projetos, bg=p["window_bg"])
        self.container_projetos.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # Canvas para scrollbar
        self.canvas_projetos = tk.Canvas(
            self.container_projetos,
            bg=p["window_bg"],
            highlightthickness=0,
            width=160
        )
        self.canvas_projetos.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # Scrollbar
        self.scrollbar_projetos = tk.Scrollbar(
            self.container_projetos,
            orient="vertical",
            command=self.canvas_projetos.yview
        )
        self.scrollbar_projetos.pack(side=tk.RIGHT, fill=tk.Y)

        self.canvas_projetos.configure(yscrollcommand=self.scrollbar_projetos.set)

        # Frame interno para os projetos
        self.scroll_projetos = tk.Frame(self.canvas_projetos, bg=p["window_bg"])
        self.canvas_window = self.canvas_projetos.create_window(
            (0, 0),
            window=self.scroll_projetos,
            anchor="nw",
            width=160
        )

        # Bind para ajustar scroll region
        self.scroll_projetos.bind(
            "<Configure>",
            lambda e: self.canvas_projetos.configure(scrollregion=self.canvas_projetos.bbox("all"))
        )

        # Atualiza a lista de projetos
        self.atualizar_lista_projetos()

    def atualizar_lista_projetos(self):
        """Atualiza a lista de projetos no painel lateral com preview de cores"""
        for w in self.scroll_projetos.winfo_children():
            w.destroy()

        p = self.paletas[self.tema.get()]

        if not self.projetos:
            tk.Label(
                self.scroll_projetos,
                text="Nenhum projeto salvo",
                bg=p["window_bg"],
                fg="#888888",
                font=("Arial", 8, "italic")
            ).pack(pady=20)
            return

        # Ordena projetos por data de modificação (mais recente primeiro)
        projetos_ordenados = sorted(
            self.projetos.items(),
            key=lambda x: x[1].get("data_modificacao", ""),
            reverse=True
        )

        for nome, dados in projetos_ordenados[:20]:  # Mostra até 20 projetos recentes
            frame_item = tk.Frame(self.scroll_projetos, bg=p["window_bg"])
            frame_item.pack(fill=tk.X, pady=3)

            # Container principal do item
            frame_conteudo = tk.Frame(frame_item, bg=p["window_bg"])
            frame_conteudo.pack(fill=tk.X, expand=True)

            # Frame para botão e menu
            frame_botoes = tk.Frame(frame_conteudo, bg=p["window_bg"])
            frame_botoes.pack(fill=tk.X)

            # Botão do projeto
            is_ativo = nome == self.projeto_atual
            btn_texto = nome[:16] + "..." if len(nome) > 16 else nome

            btn = tk.Button(
                frame_botoes,
                text=btn_texto,
                bg=p["special"] if is_ativo else p["btn"],
                fg="#ffffff" if is_ativo else p["text_fg"],
                relief=tk.FLAT,
                command=lambda n=nome: self.carregar_projeto(n),
                width=14,
                anchor=tk.W,
                font=("Arial", 8, "bold" if is_ativo else "normal")
            )
            btn.pack(side=tk.LEFT, fill=tk.X, expand=True)

            # Botão de menu (3 pontos)
            btn_menu = tk.Button(
                frame_botoes,
                text="⋮",
                bg=p["window_bg"],
                fg=p["text_fg"],
                relief=tk.FLAT,
                width=2,
                font=("Arial", 10, "bold"),
                command=lambda n=nome, b=btn: self.mostrar_menu_projeto(n, b)
            )
            btn_menu.pack(side=tk.RIGHT)

            # Tooltip com info
            num_cores = dados.get("num_cores", len(dados.get("cores_hex", [])))
            data_mod = dados.get("data_modificacao", "")
            if data_mod:
                try:
                    dt = datetime.fromisoformat(data_mod)
                    data_str = dt.strftime("%d/%m/%y %H:%M")
                except:
                    data_str = data_mod[:10]
            else:
                data_str = "Sem data"

            tooltip_text = f"{num_cores} cores • {data_str}"
            # Adiciona tooltip simples
            for widget in [frame_item, frame_conteudo]:
                widget.bind("<Enter>", lambda e, t=tooltip_text: self.mostrar_tooltip(e, t))
                widget.bind("<Leave>", lambda e: self.esconder_tooltip())

    def mostrar_menu_projeto(self, nome_projeto, parent_widget):
        """Mostra menu de contexto para um projeto"""
        menu = tk.Menu(self.root, tearoff=0)
        menu.add_command(label="Carregar", command=lambda: self.carregar_projeto(nome_projeto))
        menu.add_command(label="Renomear", command=lambda: self.renomear_projeto(nome_projeto))
        menu.add_separator()
        menu.add_command(label="Excluir", command=lambda: self.excluir_projeto(nome_projeto))

        # Posiciona o menu
        x = parent_widget.winfo_rootx()
        y = parent_widget.winfo_rooty() + parent_widget.winfo_height()
        menu.post(x, y)

    def criar_novo_projeto(self):
        """Cria um novo projeto (limpa o canvas)"""
        self.salvar_estado("Novo projeto")
        self.cores_hex = []
        self.cor_atual = "#0078d7"
        self.projeto_atual = None
        self.desenhar_gradiente()
        self.atualizar_lista_projetos()
        self.label_info.config(text="Novo projeto criado", fg="#2196f3")

    def salvar_projeto_atual(self, nome=None):
        """Salva o projeto atual"""
        if not self.cores_hex:
            messagebox.showinfo("Salvar Projeto", "Nenhuma cor para salvar.", parent=self.root)
            return False

        if nome is None:
            nome = self.projeto_atual

        if nome is None:
            return False

        # Salva o projeto
        self.projetos[nome] = {
            "cores_hex": self.cores_hex.copy(),
            "cor_atual": self.cor_atual,
            "data_criacao": self.projetos.get(nome, {}).get("data_criacao", datetime.now().isoformat()),
            "data_modificacao": datetime.now().isoformat(),
            "num_cores": len(self.cores_hex)
        }

        self.projeto_atual = nome
        self.salvar_projetos()
        self.atualizar_lista_projetos()
        return True

    def abrir_salvar_projeto(self):
        """Abre diálogo para salvar projeto"""
        win = tk.Toplevel(self.root)
        win.title("Salvar Projeto")
        win.geometry("350x180")
        win.attributes("-topmost", True)
        win.resizable(False, False)
        win.transient(self.root)
        win.grab_set()

        p = self.paletas[self.tema.get()]
        win.config(bg=p["window_bg"])

        tk.Label(
            win,
            text="Nome do Projeto:",
            bg=p["window_bg"],
            fg=p["text_fg"],
            font=("Arial", 10, "bold")
        ).pack(pady=(20, 10))

        nome_var = tk.StringVar(value=self.projeto_atual if self.projeto_atual else f"Projeto {len(self.projetos) + 1}")
        entry = tk.Entry(win, textvariable=nome_var, width=30, font=("Arial", 11))
        entry.pack(pady=5)
        entry.select_range(0, tk.END)
        entry.focus()

        def salvar():
            nome = nome_var.get().strip()
            if not nome:
                messagebox.showwarning("Aviso", "Digite um nome para o projeto.", parent=win)
                return

            if nome in self.projetos and nome != self.projeto_atual:
                if not messagebox.askyesno(
                    "Substituir?",
                    f'Já existe um projeto "{nome}". Deseja substituir?',
                    parent=win
                ):
                    return

            if self.salvar_projeto_atual(nome):
                self.label_info.config(text=f"Projeto salvo: {nome}", fg="#2e7d32")
            win.destroy()

        def cancelar():
            win.destroy()

        frame_botoes = tk.Frame(win, bg=p["window_bg"])
        frame_botoes.pack(pady=20)

        tk.Button(
            frame_botoes,
            text="Cancelar",
            command=cancelar,
            bg=p["btn"],
            fg=p["text_fg"],
            width=10
        ).pack(side=tk.LEFT, padx=5)

        tk.Button(
            frame_botoes,
            text="Salvar",
            command=salvar,
            bg="#4caf50",
            fg="white",
            width=10,
            font=("Arial", 9, "bold")
        ).pack(side=tk.LEFT, padx=5)

        entry.bind("<Return>", lambda e: salvar())

    def abrir_gerenciar_projetos(self):
        """Abre janela de gerenciamento de projetos"""
        win = tk.Toplevel(self.root)
        win.title("Gerenciar Projetos")
        win.geometry("500x450")
        win.attributes("-topmost", True)
        win.resizable(False, False)
        p = self.paletas[self.tema.get()]
        win.config(bg=p["window_bg"])

        tk.Label(
            win,
            text="📂 Meus Projetos",
            bg=p["window_bg"],
            fg=p["text_fg"],
            font=("Arial", 14, "bold")
        ).pack(pady=(20, 10))

        # Container com scrollbar
        frame_container = tk.Frame(win, bg=p["window_bg"])
        frame_container.pack(fill=tk.BOTH, expand=True, padx=20, pady=10)

        canvas = tk.Canvas(frame_container, bg=p["window_bg"], highlightthickness=0)
        scrollbar = tk.Scrollbar(frame_container, orient="vertical", command=canvas.yview)
        scroll_frame = tk.Frame(canvas, bg=p["window_bg"])

        scroll_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )

        canvas.create_window((0, 0), window=scroll_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        def atualizar_lista():
            for w in scroll_frame.winfo_children():
                w.destroy()

            if not self.projetos:
                tk.Label(
                    scroll_frame,
                    text="Nenhum projeto salvo",
                    bg=p["window_bg"],
                    fg="#888888",
                    font=("Arial", 10)
                ).pack(pady=50)
                return

            # Ordena por data de modificação
            projetos_ordenados = sorted(
                self.projetos.items(),
                key=lambda x: x[1].get("data_modificacao", ""),
                reverse=True
            )

            for nome, dados in projetos_ordenados:
                frame_proj = tk.Frame(scroll_frame, bg=p["canvas"], padx=10, pady=8)
                frame_proj.pack(fill=tk.X, pady=3)

                # Info do projeto
                frame_info = tk.Frame(frame_proj, bg=p["canvas"])
                frame_info.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

                tk.Label(
                    frame_info,
                    text=nome,
                    bg=p["canvas"],
                    fg=p["text_fg"],
                    font=("Arial", 10, "bold"),
                    anchor=tk.W
                ).pack(fill=tk.X)

                num_cores = dados.get("num_cores", len(dados.get("cores_hex", [])))
                data_mod = dados.get("data_modificacao", "")
                if data_mod:
                    try:
                        dt = datetime.fromisoformat(data_mod)
                        data_str = dt.strftime("%d/%m/%Y %H:%M")
                    except:
                        data_str = data_mod
                else:
                    data_str = "Sem data"

                tk.Label(
                    frame_info,
                    text=f"{num_cores} cores • {data_str}",
                    bg=p["canvas"],
                    fg="#888888",
                    font=("Arial", 8),
                    anchor=tk.W
                ).pack(fill=tk.X)

                # Botões de ação
                frame_acoes = tk.Frame(frame_proj, bg=p["canvas"])
                frame_acoes.pack(side=tk.RIGHT)

                tk.Button(
                    frame_acoes,
                    text="Carregar",
                    command=lambda n=nome: [self.carregar_projeto(n), win.destroy()],
                    bg=p["special"],
                    fg="white",
                    relief=tk.FLAT,
                    width=8
                ).pack(side=tk.LEFT, padx=2)

                tk.Button(
                    frame_acoes,
                    text="Excluir",
                    command=lambda n=nome, f=frame_proj: confirmar_excluir(n, f),
                    bg="#e57373",
                    fg="white",
                    relief=tk.FLAT,
                    width=8
                ).pack(side=tk.LEFT, padx=2)

        def confirmar_excluir(nome, widget):
            if messagebox.askyesno(
                "Confirmar",
                f'Deseja excluir o projeto "{nome}"?',
                parent=win
            ):
                self.excluir_projeto(nome)
                widget.destroy()
                if not self.projetos:
                    atualizar_lista()

        atualizar_lista()

        # Botão fechar
        tk.Button(
            win,
            text="Fechar",
            command=win.destroy,
            bg=p["btn"],
            fg=p["text_fg"],
            width=12
        ).pack(pady=15)

    def carregar_projeto(self, nome):
        """Carrega um projeto salvo"""
        if nome not in self.projetos:
            return

        dados = self.projetos[nome]

        self.salvar_estado(f"Carregar projeto: {nome}")
        self.cores_hex = dados.get("cores_hex", [])
        self.cor_atual = dados.get("cor_atual", "#0078d7")
        self.projeto_atual = nome

        self.desenhar_gradiente()
        self.atualizar_label_info()
        self.atualizar_lista_projetos()

        self.label_info.config(text=f"Projeto carregado: {nome}", fg="#2196f3")

    def renomear_projeto(self, nome_antigo):
        """Renomeia um projeto"""
        if nome_antigo not in self.projetos:
            return

        win = tk.Toplevel(self.root)
        win.title("Renomear Projeto")
        win.geometry("300x120")
        win.attributes("-topmost", True)
        win.resizable(False, False)
        win.transient(self.root)
        win.grab_set()

        p = self.paletas[self.tema.get()]
        win.config(bg=p["window_bg"])

        tk.Label(
            win,
            text="Novo nome:",
            bg=p["window_bg"],
            fg=p["text_fg"]
        ).pack(pady=(15, 5))

        novo_nome_var = tk.StringVar(value=nome_antigo)
        entry = tk.Entry(win, textvariable=novo_nome_var, width=25)
        entry.pack()
        entry.select_range(0, tk.END)
        entry.focus()

        def confirmar():
            novo_nome = novo_nome_var.get().strip()
            if not novo_nome:
                return
            if novo_nome in self.projetos and novo_nome != nome_antigo:
                messagebox.showwarning("Aviso", "Já existe um projeto com este nome.", parent=win)
                return

            # Renomeia
            self.projetos[novo_nome] = self.projetos.pop(nome_antigo)
            if self.projeto_atual == nome_antigo:
                self.projeto_atual = novo_nome

            self.salvar_projetos()
            self.atualizar_lista_projetos()
            win.destroy()

        def cancelar():
            win.destroy()

        frame = tk.Frame(win, bg=p["window_bg"])
        frame.pack(pady=15)

        tk.Button(frame, text="Cancelar", command=cancelar).pack(side=tk.LEFT, padx=5)
        tk.Button(frame, text="Renomear", command=confirmar, bg="#2196f3", fg="white").pack(side=tk.LEFT, padx=5)

        entry.bind("<Return>", lambda e: confirmar())

    def excluir_projeto(self, nome):
        """Exclui um projeto"""
        if nome in self.projetos:
            del self.projetos[nome]
            if self.projeto_atual == nome:
                self.projeto_atual = None
            self.salvar_projetos()
            self.atualizar_lista_projetos()
            self.label_info.config(text=f"Projeto excluído: {nome}", fg="#ff9800")

    # Tooltip para projetos
    def mostrar_tooltip(self, event, texto):
        """Mostra um tooltip temporário"""
        self.tooltip = tk.Toplevel(self.root)
        self.tooltip.wm_overrideredirect(True)
        self.tooltip.wm_geometry(f"+{event.x_root + 10}+{event.y_root + 10}")

        p = self.paletas[self.tema.get()]
        lbl = tk.Label(
            self.tooltip,
            text=texto,
            bg="#333333",
            fg="#ffffff",
            font=("Arial", 8),
            padx=8,
            pady=4
        )
        lbl.pack()

    def esconder_tooltip(self):
        """Esconde o tooltip"""
        if hasattr(self, 'tooltip') and self.tooltip:
            try:
                self.tooltip.destroy()
            except:
                pass
            self.tooltip = None

    def salvar_projeto_rapido(self, event=None):
        """Salva o projeto atual rapidamente (Ctrl+S)"""
        if not self.cores_hex:
            messagebox.showinfo("Salvar Projeto", "Nenhuma cor para salvar.", parent=self.root)
            return "break"

        # Se já tem um projeto carregado, salva nele
        if self.projeto_atual:
            if self.salvar_projeto_atual(self.projeto_atual):
                self.label_info.config(text=f"✓ Projeto salvo: {self.projeto_atual}", fg="#2e7d32")
            return "break"

        # Se não tem projeto, abre o diálogo
        self.abrir_salvar_projeto()
        return "break"

    # SALVAMENTO
    def salvar_configuracoes(self):
        try:
            config_data = {
                "tema": self.tema.get(),
                "sim_daltonismo": self.sim_daltonismo.get(),
                "passo_delta": self.passo_delta.get(),
                "brilho": self.adj_bright.get(),
                "contraste": self.adj_contrast.get(),
                "gamma": self.adj_gamma.get(),
                "saturacao": self.adj_sat.get(),
                "matiz": self.adj_hue.get(),
                "temperatura": self.adj_temp.get(),
                "mostrar_preview_contraste": self.mostrar_preview_contraste.get(),
                "mostrar_wcag": self.mostrar_wcag.get(),
                "wcag_fundo": self.wcag_fundo_var.get(),
                "ultima_atividade": self.ultima_atividade,
                "ultima_cor": self.cor_atual
            }
            with open(self.arquivo_config, "w") as f:
                json.dump(config_data, f, indent=4)
        except Exception as e:
            print(f"Erro ao salvar configurações: {e}")

    def carregar_configuracoes(self):
        if os.path.exists(self.arquivo_config):
            try:
                with open(self.arquivo_config, "r") as f:
                    data = json.load(f)
                    self.tema.set(data.get("tema", "claro"))
                    self.sim_daltonismo.set(data.get("sim_daltonismo", "normal"))
                    self.passo_delta.set(data.get("passo_delta", 1.5))
                    self.adj_bright.set(data.get("brilho", 0))
                    self.adj_contrast.set(data.get("contraste", 1.0))
                    self.adj_gamma.set(data.get("gamma", 1.0))
                    self.adj_sat.set(data.get("saturacao", 1.0))
                    self.adj_hue.set(data.get("matiz", 0))
                    self.adj_temp.set(data.get("temperatura", 6500))
                    self.mostrar_preview_contraste.set(data.get("mostrar_preview_contraste", True))
                    self.mostrar_wcag.set(data.get("mostrar_wcag", True))
                    self.wcag_fundo_var.set(data.get("wcag_fundo", "preto_branco"))
                    self.ultima_atividade = data.get("ultima_atividade", "")
                    self.cor_atual = data.get("ultima_cor", "#0078d7")
            except Exception as e:
                print(f"Erro ao carregar configurações: {e}")

    def ao_fechar(self):
        if self._debounce_timer:
            self.root.after_cancel(self._debounce_timer)
        self.ultima_atividade = f"Trabalhando com a paleta base {self.cor_atual}"
        self.salvar_configuracoes()
        self.salvar_projetos()
        self.root.destroy()

    def mostrar_memoria_inicial(self):
        """Mostra uma mensagem lembrando o que estava sendo feito na última sessão"""
        if self.ultima_atividade:
            self.root.after(500, lambda: self.label_info.config(
                text=f"Bem-vindo de volta! {self.ultima_atividade}",
                fg="#2196f3"
            ))
            # Retorna ao texto normal após 5 segundos
            self.root.after(5500, lambda: self.label_info.config(
                text=f"Color Lab Pro v4.6 | Base: {self.cor_atual}",
                fg=self.paletas[self.tema.get()]["text_fg"]
            ))

    # ── SISTEMA UNDO/REDO ────────────────────────────────────────────────────

    def salvar_estado(self, descricao="Ação"):
        """Salva o estado atual (cores_hex + cor_atual) na pilha de undo."""
        if self._salvando_estado:
            return

        self._salvando_estado = True

        # Cria uma cópia profunda do estado atual
        estado = {
            "cores_hex": self.cores_hex.copy() if self.cores_hex else [],
            "cor_atual": self.cor_atual,
            "descricao": descricao
        }

        # Adiciona à pilha de undo
        self._undo_stack.append(estado)

        # Limita o tamanho da pilha
        if len(self._undo_stack) > self._max_undo_states:
            self._undo_stack.pop(0)

        # Limpa a pilha de redo quando uma nova ação é realizada
        self._redo_stack.clear()

        self._salvando_estado = False

    def undo(self, event=None):
        """Desfaz a última ação (Ctrl+Z)."""
        if not self._undo_stack:
            self.label_info.config(text="Nada para desfazer", fg="#ff9800")
            return "break"

        # Salva o estado atual na pilha de redo
        estado_atual = {
            "cores_hex": self.cores_hex.copy() if self.cores_hex else [],
            "cor_atual": self.cor_atual,
            "descricao": "Estado atual"
        }
        self._redo_stack.append(estado_atual)

        # Restaura o estado anterior
        estado_anterior = self._undo_stack.pop()
        self._restaurar_estado(estado_anterior)

        descricao = estado_anterior.get("descricao", "Ação")
        self.label_info.config(text=f"Desfeito: {descricao} ({len(self._undo_stack)} disponíveis)", fg="#2196f3")
        return "break"

    def redo(self, event=None):
        """Refaz a última ação desfeita (Ctrl+Y)."""
        if not self._redo_stack:
            self.label_info.config(text="Nada para refazer", fg="#ff9800")
            return "break"

        # Salva o estado atual na pilha de undo
        estado_atual = {
            "cores_hex": self.cores_hex.copy() if self.cores_hex else [],
            "cor_atual": self.cor_atual,
            "descricao": "Estado atual"
        }
        self._undo_stack.append(estado_atual)

        # Restaura o estado do redo
        estado_redo = self._redo_stack.pop()
        self._restaurar_estado(estado_redo)

        descricao = estado_redo.get("descricao", "Ação")
        self.label_info.config(text=f"Refeito: {descricao} ({len(self._redo_stack)} disponíveis)", fg="#4caf50")
        return "break"

    def _restaurar_estado(self, estado):
        """Restaura o estado a partir de um dicionário."""
        self._salvando_estado = True

        self.cores_hex = estado["cores_hex"].copy() if estado["cores_hex"] else []
        self.cor_atual = estado["cor_atual"]

        # Atualiza a UI
        self.desenhar_gradiente()
        self.atualizar_label_info()

        self._salvando_estado = False

    # NAVEGAÇÃO CONFIGS
    def abrir_configuracoes(self):
        if self.config_win is None or not tk.Toplevel.winfo_exists(self.config_win):
            self.config_win = tk.Toplevel(self.root)
            self.config_win.title("Configurações")
            self.config_win.geometry("450x680")
            self.config_win.attributes("-topmost", True)
            self.config_container = tk.Frame(self.config_win)
            self.config_container.pack(fill=tk.BOTH, expand=True)
            self.tela_menu_config()
            # Salva ao fechar a janela de config também
            self.config_win.protocol("WM_DELETE_WINDOW", lambda: [self.salvar_configuracoes(), self.config_win.destroy()])
        else:
            self.config_win.focus_set()

    def tela_menu_config(self):
        for w in self.config_container.winfo_children(): w.destroy()
        p = self.paletas[self.tema.get()]
        self.config_win.config(bg=p["window_bg"])
        self.config_container.config(bg=p["window_bg"])
        tk.Label(self.config_container, text="MENU", font=("Arial", 12, "bold")).pack(pady=30)
        tk.Button(self.config_container, text="🖥️ Interface", command=self.tela_interface, width=25).pack(pady=10)
        tk.Button(self.config_container, text="🎞️ Ajustes", command=self.tela_ajustes, width=25).pack(pady=10)
        tk.Button(self.config_container, text="👁️ Acessibilidade", command=self.tela_modos, width=25).pack(pady=10)
        self.aplicar_tema()

    def tela_interface(self):
        for w in self.config_container.winfo_children(): w.destroy()
        tk.Button(self.config_container, text="⬅ Voltar", command=self.tela_menu_config).pack(anchor=tk.NW, padx=10, pady=10)
        tk.Label(self.config_container, text="TEMA", font=("Arial", 11, "bold")).pack(pady=10)
        tk.Radiobutton(self.config_container, text="Claro", variable=self.tema, value="claro", command=self.aplicar_tema).pack(pady=5)
        tk.Radiobutton(self.config_container, text="Escuro", variable=self.tema, value="escuro", command=self.aplicar_tema).pack(pady=5)

        tk.Label(self.config_container, text="OPÇÕES DE EXIBIÇÃO", font=("Arial", 11, "bold")).pack(pady=(20, 10))
        tk.Checkbutton(self.config_container, text="Mostrar preview de contraste (Aa)",
                       variable=self.mostrar_preview_contraste,
                       command=self.desenhar_gradiente).pack(pady=5)
        tk.Checkbutton(self.config_container, text="Mostrar badge WCAG no canvas",
                       variable=self.mostrar_wcag,
                       command=self.desenhar_gradiente).pack(pady=5)

        tk.Label(self.config_container, text="FUNDO DE REFERÊNCIA WCAG",
                 font=("Arial", 11, "bold")).pack(pady=(20, 6))
        tk.Label(self.config_container,
                 text="Qual cor usar como fundo ao calcular\na razão de contraste de cada swatch:",
                 font=("Arial", 8), justify=tk.CENTER).pack()

        for texto, valor in [
            ("Melhor entre branco e preto (padrão)", "preto_branco"),
            ("Branco (#ffffff)", "branco"),
            ("Preto (#000000)", "preto"),
        ]:
            tk.Radiobutton(self.config_container, text=texto,
                           variable=self.wcag_fundo_var, value=valor,
                           command=self.desenhar_gradiente).pack(anchor=tk.W, padx=60, pady=2)

        # Fundo customizado
        frame_custom = tk.Frame(self.config_container)
        frame_custom.pack(pady=(6, 2))
        tk.Label(frame_custom, text="Cor customizada:").pack(side=tk.LEFT, padx=4)
        self._wcag_custom_hex = tk.StringVar(
            value=self.wcag_fundo_var.get()
                  if self.wcag_fundo_var.get().startswith("#") else "#ffffff")
        entry_custom = tk.Entry(frame_custom, textvariable=self._wcag_custom_hex,
                                width=9, font=("Courier", 10))
        entry_custom.pack(side=tk.LEFT, padx=2)

        def aplicar_custom(*_):
            val = self._wcag_custom_hex.get().strip()
            if not val.startswith("#"):
                val = "#" + val
            val = val[:7]
            try:
                hex_to_rgb(val)
                self.wcag_fundo_var.set(val)
                self.desenhar_gradiente()
            except Exception:
                pass

        tk.Button(frame_custom, text="Aplicar", command=aplicar_custom,
                  font=("Arial", 8)).pack(side=tk.LEFT, padx=4)
        entry_custom.bind("<Return>", aplicar_custom)

        self.aplicar_tema()

    def tela_ajustes(self):
        for w in self.config_container.winfo_children(): w.destroy()
        tk.Button(self.config_container, text="⬅ Voltar", command=self.tela_menu_config).pack(anchor=tk.NW, padx=10, pady=10)
        tk.Label(self.config_container, text="AJUSTES", font=("Arial", 11, "bold")).pack(pady=5)

        # Debounce para sliders - evita redesenhar a cada frame
        def debounced_draw(is_delta=False):
            if self._debounce_timer:
                self.root.after_cancel(self._debounce_timer)
            def draw():
                if is_delta:
                    self.gerar_lista_cores(self.cor_atual)
                else:
                    self.desenhar_gradiente()
            self._debounce_timer = self.root.after(self._debounce_delay, draw)

        def sld(l, v, d, a, r, is_delta=False):
            tk.Label(self.config_container, text=l).pack()
            cmd = lambda e: debounced_draw(is_delta)
            tk.Scale(self.config_container, from_=d, to=a, resolution=r, orient=tk.HORIZONTAL, variable=v, command=cmd, highlightthickness=0).pack(fill=tk.X, padx=40)
        
        sld("Brilho", self.adj_bright, -100, 100, 1)
        sld("Contraste", self.adj_contrast, 0.5, 2.0, 0.05)
        sld("Gamma", self.adj_gamma, 0.1, 3.0, 0.1)
        sld("Saturação", self.adj_sat, 0.0, 2.0, 0.1)
        sld("Matiz", self.adj_hue, -180, 180, 1)
        sld("Temperatura", self.adj_temp, 1000, 12000, 100)
        sld("Nitidez", self.passo_delta, 0.1, 10.0, 0.1, is_delta=True)
        
        tk.Button(self.config_container, text="🔄 Restaurar Padrões", command=self.resetar_ajustes, bg="#ffcdd2", fg="black").pack(pady=20)
        self.aplicar_tema()

    def tela_modos(self):
        for w in self.config_container.winfo_children(): w.destroy()
        tk.Button(self.config_container, text="⬅ Voltar", command=self.tela_menu_config).pack(anchor=tk.NW, padx=10, pady=10)
        tk.Label(self.config_container, text="MODOS", font=("Arial", 11, "bold")).pack(pady=10)
        for t, v in [("Normal", "normal"), ("Deuteranopia (Verde-Vermelho)", "deuteranopia"), ("Protanopia (Vermelho-Verde)", "protanopia"), ("Tritanopia (Azul-Amarelo)", "tritanopia"), ("Acromatopsia (Monocromacia)", "acromatopsia")]:
            tk.Radiobutton(self.config_container, text=t, variable=self.sim_daltonismo, value=v, command=self.desenhar_gradiente).pack(anchor=tk.W, padx=100, pady=5)
        self.aplicar_tema()

    def resetar_ajustes(self):
        self.adj_bright.set(0); self.adj_contrast.set(1.0); self.adj_gamma.set(1.0); self.adj_sat.set(1.0); self.adj_hue.set(0); self.adj_temp.set(6500); self.passo_delta.set(1.5); self.sim_daltonismo.set("normal")
        self.gerar_lista_cores(self.cor_atual); self.salvar_configuracoes()

    # ── PALETAS HARMÔNICAS ───────────────────────────────────────────────────

    def abrir_harmonias(self):
        """Abre a janela de geração de paletas harmônicas em LCH."""
        win = tk.Toplevel(self.root)
        win.title("Paletas Harmônicas — LCH")
        win.geometry("700x560")
        win.attributes("-topmost", True)
        win.resizable(False, False)
        p = self.paletas[self.tema.get()]
        win.config(bg=p["window_bg"])

        # ── Estado interno da janela ─────────────────────────────────────────
        cor_base_var   = tk.StringVar(value=self.cor_atual)
        harmonia_var   = tk.StringVar(value=list(HARMONIAS.keys())[0])
        angulo_var     = tk.IntVar(value=30)   # usado apenas pela Análoga
        lch_cache      = {}                    # cache das cores geradas

        # ── Cabeçalho ────────────────────────────────────────────────────────
        frame_topo = tk.Frame(win, bg=p["window_bg"], pady=10)
        frame_topo.pack(fill=tk.X, padx=16)

        tk.Label(frame_topo, text="Cor base:",
                 bg=p["window_bg"], fg=p["text_fg"],
                 font=("Arial", 10)).grid(row=0, column=0, sticky=tk.W)

        entry_hex = tk.Entry(frame_topo, textvariable=cor_base_var, width=10,
                             font=("Courier", 11))
        entry_hex.grid(row=0, column=1, padx=6)

        preview_base = tk.Label(frame_topo, width=3, bg=self.cor_atual,
                                relief=tk.FLAT)
        preview_base.grid(row=0, column=2, padx=4)

        def escolher_base():
            cor = colorchooser.askcolor(title="Escolher cor base",
                                        color=cor_base_var.get(),
                                        parent=win)[1]
            if cor:
                cor_base_var.set(cor)
                atualizar_tudo()

        tk.Button(frame_topo, text="🎨", command=escolher_base,
                  bg=p["btn"], fg=p["text_fg"], relief=tk.FLAT).grid(row=0, column=3, padx=4)

        # ── Seletor de harmonia ──────────────────────────────────────────────
        tk.Label(frame_topo, text="Harmonia:",
                 bg=p["window_bg"], fg=p["text_fg"],
                 font=("Arial", 10)).grid(row=0, column=4, sticky=tk.W, padx=(20, 0))

        menu_harm = tk.OptionMenu(frame_topo, harmonia_var,
                                  *HARMONIAS.keys(),
                                  command=lambda _: atualizar_tudo())
        menu_harm.config(bg=p["btn"], fg=p["text_fg"], relief=tk.FLAT,
                         activebackground=p["special"])
        menu_harm.grid(row=0, column=5, padx=6)

        lbl_desc = tk.Label(frame_topo, text="",
                            bg=p["window_bg"], fg="#888888",
                            font=("Arial", 8, "italic"))
        lbl_desc.grid(row=1, column=0, columnspan=6, sticky=tk.W, pady=(2, 0))

        # Controle de ângulo — visível apenas para Análoga
        frame_angulo = tk.Frame(win, bg=p["window_bg"])
        frame_angulo.pack(fill=tk.X, padx=16)
        lbl_ang = tk.Label(frame_angulo, text="Ângulo analógico:",
                           bg=p["window_bg"], fg=p["text_fg"], font=("Arial", 9))
        sld_ang = tk.Scale(frame_angulo, from_=10, to=60, orient=tk.HORIZONTAL,
                           variable=angulo_var, bg=p["window_bg"], fg=p["text_fg"],
                           highlightthickness=0, troughcolor=p["canvas"],
                           command=lambda _: atualizar_tudo())
        lbl_ang_val = tk.Label(frame_angulo, textvariable=angulo_var,
                               bg=p["window_bg"], fg=p["text_fg"], width=3,
                               font=("Arial", 9))

        # ── Roda LCH (círculo cromático visual) ─────────────────────────────
        frame_roda = tk.Frame(win, bg=p["window_bg"])
        frame_roda.pack(pady=6)
        canvas_roda = tk.Canvas(frame_roda, width=200, height=200,
                                bg=p["window_bg"], highlightthickness=0)
        canvas_roda.pack(side=tk.LEFT, padx=16)

        # Painel de swatches + info
        frame_swatches = tk.Frame(frame_roda, bg=p["window_bg"])
        frame_swatches.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=8)

        # ── Canvas de gradiente expandido ────────────────────────────────────
        frame_grad = tk.Frame(win, bg=p["window_bg"])
        frame_grad.pack(fill=tk.X, padx=16, pady=4)
        canvas_grad = tk.Canvas(frame_grad, height=60, bg=p["canvas"],
                                highlightthickness=0)
        canvas_grad.pack(fill=tk.X)

        # ── Botões de ação ───────────────────────────────────────────────────
        frame_acoes = tk.Frame(win, bg=p["window_bg"], pady=8)
        frame_acoes.pack(fill=tk.X, padx=16)

        def usar_no_canvas():
            cores = lch_cache.get("cores", [])
            if cores:
                self.salvar_estado(f"Harmonia: {harmonia_var.get()}")
                self.cores_hex = cores
                self.cor_atual = cores[0]
                self.adicionar_historico(cores[0])
                self.atualizar_label_info()
                self.desenhar_gradiente()
                self.label_info.config(
                    text=f"Harmonia aplicada: {harmonia_var.get()} | {len(cores)} cores",
                    fg="#2e7d32")
                win.destroy()

        def gerar_gradiente_harmonico():
            """Gera gradiente perceptual entre todas as cores da harmonia."""
            cores = lch_cache.get("cores", [])
            if not cores:
                return
            self.salvar_estado(f"Gradiente harmônico: {harmonia_var.get()}")
            resultado = []
            for i in range(len(cores) - 1):
                lab_a = xyz_to_lab(rgb_to_xyz(hex_to_rgb(cores[i])))
                lab_b = xyz_to_lab(rgb_to_xyz(hex_to_rgb(cores[i + 1])))
                dist = delta_e_cie76(lab_a, lab_b)
                passos = max(3, int(dist / self.passo_delta.get()))
                for k in range(passos):
                    t = k / (passos - 1) if passos > 1 else 0
                    curr = tuple(lab_a[j] + (lab_b[j] - lab_a[j]) * t for j in range(3))
                    resultado.append(rgb_to_hex(xyz_to_rgb(lab_to_xyz(curr))))
            self.cores_hex = resultado
            self.cor_atual = cores[0]
            self.adicionar_historico(cores[0])
            self.atualizar_label_info()
            self.desenhar_gradiente()
            self.label_info.config(
                text=f"Gradiente harmônico: {harmonia_var.get()} | {len(resultado)} passos",
                fg="#6a1b9a")
            win.destroy()

        tk.Button(frame_acoes, text="✅ Usar swatches no canvas",
                  command=usar_no_canvas, bg="#c8e6c9", fg="#1b5e20",
                  font=("Arial", 9, "bold"), relief=tk.FLAT, padx=8).pack(side=tk.LEFT, padx=4)
        tk.Button(frame_acoes, text="🌈 Gerar gradiente entre harmônicas",
                  command=gerar_gradiente_harmonico, bg="#e1bee7", fg="#4a148c",
                  font=("Arial", 9, "bold"), relief=tk.FLAT, padx=8).pack(side=tk.LEFT, padx=4)
        tk.Button(frame_acoes, text="✖ Fechar",
                  command=win.destroy, bg=p["btn"], fg=p["text_fg"],
                  relief=tk.FLAT, padx=8).pack(side=tk.RIGHT, padx=4)

        # ── Funções de renderização ──────────────────────────────────────────
        RAIO = 80
        CX, CY = 100, 100

        def desenhar_roda(cores_harm):
            """Desenha o círculo cromático LCH com as cores da harmonia marcadas."""
            canvas_roda.delete("all")
            # Anel externo com segmentos de cor
            N = 360
            for grau in range(N):
                lch_seg = hex_para_lch(cor_base_var.get())
                L, C, _ = lch_seg
                hex_seg = lch_para_hex((max(40, min(70, L)), max(30, C), grau))
                ang_rad = math.radians(grau - 90)
                ang_rad2 = math.radians(grau + 1 - 90)
                x1 = CX + (RAIO - 14) * math.cos(ang_rad)
                y1 = CY + (RAIO - 14) * math.sin(ang_rad)
                x2 = CX + RAIO * math.cos(ang_rad)
                y2 = CY + RAIO * math.sin(ang_rad)
                x3 = CX + RAIO * math.cos(ang_rad2)
                y3 = CY + RAIO * math.sin(ang_rad2)
                x4 = CX + (RAIO - 14) * math.cos(ang_rad2)
                y4 = CY + (RAIO - 14) * math.sin(ang_rad2)
                try:
                    canvas_roda.create_polygon(x1, y1, x2, y2, x3, y3, x4, y4,
                                               fill=hex_seg, outline=hex_seg)
                except Exception:
                    pass

            # Marcadores das cores harmônicas sobre o anel
            for i, cor in enumerate(cores_harm):
                try:
                    lch_c = hex_para_lch(cor)
                    ang_rad = math.radians(lch_c[2] - 90)
                    mx = CX + (RAIO - 7) * math.cos(ang_rad)
                    my = CY + (RAIO - 7) * math.sin(ang_rad)
                    r_dot = 7 if i == 0 else 5
                    borda = "#000000" if i == 0 else "#ffffff"
                    canvas_roda.create_oval(mx - r_dot, my - r_dot,
                                            mx + r_dot, my + r_dot,
                                            fill=cor, outline=borda, width=2)
                    if i == 0:
                        # Linha do centro até o marcador base
                        canvas_roda.create_line(CX, CY, mx, my,
                                                fill="#00000044", width=1, dash=(3, 3))
                except Exception:
                    pass

            # Centro com a cor base
            try:
                canvas_roda.create_oval(CX - 20, CY - 20, CX + 20, CY + 20,
                                        fill=cor_base_var.get(), outline="#00000066", width=2)
            except Exception:
                pass

        def desenhar_swatches(cores_harm):
            """Popula o painel de swatches com as cores geradas."""
            for w in frame_swatches.winfo_children():
                w.destroy()

            tk.Label(frame_swatches, text=f"{harmonia_var.get()}",
                     bg=p["window_bg"], fg=p["text_fg"],
                     font=("Arial", 10, "bold")).pack(anchor=tk.W)

            for i, cor in enumerate(cores_harm):
                try:
                    lch_c = hex_para_lch(cor)
                    rgb_c = hex_to_rgb(cor)
                    txt_fg = cor_texto_contraste(cor)

                    f = tk.Frame(frame_swatches, bg=p["window_bg"], pady=1)
                    f.pack(fill=tk.X)

                    swatch = tk.Label(f, bg=cor, width=5, height=1, relief=tk.FLAT)
                    swatch.pack(side=tk.LEFT, padx=(0, 6))

                    lbl = tk.Label(f,
                                   text=f"{cor.upper()}   L:{lch_c[0]:.0f}  C:{lch_c[1]:.0f}  H:{lch_c[2]:.0f}°",
                                   bg=p["window_bg"], fg=p["text_fg"],
                                   font=("Courier", 8))
                    lbl.pack(side=tk.LEFT)

                    # Clique no swatch copia o HEX
                    def copiar(c=cor):
                        win.clipboard_clear(); win.clipboard_append(c)
                        self.label_info.config(text=f"Copiado: {c}", fg="#2196f3")
                    swatch.bind("<Button-1>", lambda e, c=cor: copiar(c))
                    swatch.config(cursor="hand2")
                except Exception:
                    pass

        def desenhar_gradiente_preview(cores_harm):
            """Barra de gradiente mostrando as cores harmônicas em sequência."""
            canvas_grad.update_idletasks()
            w = canvas_grad.winfo_width()
            h = 60
            if w < 2 or not cores_harm:
                return
            canvas_grad.delete("all")
            larg = w / len(cores_harm)
            for i, cor in enumerate(cores_harm):
                try:
                    canvas_grad.create_rectangle(
                        i * larg, 0, (i + 1) * larg, h,
                        fill=cor, outline=cor)
                    # HEX label
                    txt_cor = cor_texto_contraste(cor)
                    canvas_grad.create_text(
                        i * larg + larg / 2, h / 2,
                        text=cor.upper(), fill=txt_cor,
                        font=("Courier", 8, "bold"))
                except Exception:
                    pass

        def atualizar_tudo(*_):
            """Ponto central de re-renderização ao mudar qualquer parâmetro."""
            # Valida hex
            hex_raw = cor_base_var.get().strip()
            if not hex_raw.startswith("#"):
                hex_raw = "#" + hex_raw
            hex_raw = hex_raw[:7]
            try:
                hex_to_rgb(hex_raw)   # lança ValueError se inválido
            except Exception:
                return
            cor_base_var.set(hex_raw)

            try:
                preview_base.config(bg=hex_raw)
            except Exception:
                pass

            # Controle de ângulo analógico
            nome = harmonia_var.get()
            if nome == "Análoga":
                lbl_ang.pack(side=tk.LEFT, padx=4)
                sld_ang.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=4)
                lbl_ang_val.pack(side=tk.LEFT)
            else:
                lbl_ang.pack_forget()
                sld_ang.pack_forget()
                lbl_ang_val.pack_forget()

            lbl_desc.config(text=HARMONIAS[nome]["desc"])

            # Gera as cores
            fn = HARMONIAS[nome]["fn"]
            try:
                if nome == "Análoga":
                    cores_harm = fn(hex_raw, angulo=angulo_var.get())
                else:
                    cores_harm = fn(hex_raw)
            except Exception as e:
                print(f"Erro ao gerar harmonia: {e}")
                return

            lch_cache["cores"] = cores_harm

            desenhar_roda(cores_harm)
            desenhar_swatches(cores_harm)
            desenhar_gradiente_preview(cores_harm)

        # Atualiza ao digitar o hex manualmente
        entry_hex.bind("<Return>", atualizar_tudo)
        entry_hex.bind("<FocusOut>", atualizar_tudo)

        # Primeiro render
        win.after(50, atualizar_tudo)
        canvas_grad.bind("<Configure>", lambda e: atualizar_tudo())

    # ── MIXER DE CORES PERCEPTUAL ────────────────────────────────────────────

    def abrir_mixer(self):
        """Mixer de cores com interpolação perceptual em LAB, LCH e RGB."""
        win = tk.Toplevel(self.root)
        win.title("Mixer de Cores Perceptual")
        win.geometry("680x580")
        win.attributes("-topmost", True)
        win.resizable(False, False)
        p   = self.paletas[self.tema.get()]
        win.config(bg=p["window_bg"])

        BG  = p["window_bg"]
        FG  = p["text_fg"]
        BTN = p["btn"]

        # ── Estado ───────────────────────────────────────────────────────────
        if self.mixer_color_a is None:
            self.mixer_color_a = self.cor_atual

        cor_a_var  = tk.StringVar(value=self.mixer_color_a)
        cor_b_var  = tk.StringVar(value=self.mixer_color_b)

        self._mixer_win = win
        self._mixer_cor_a_var = cor_a_var
        self._mixer_cor_b_var = cor_b_var

        cor_a_var.trace_add("write", lambda *_: setattr(self, 'mixer_color_a', cor_a_var.get()))
        cor_b_var.trace_add("write", lambda *_: setattr(self, 'mixer_color_b', cor_b_var.get()))

        t_var      = tk.DoubleVar(value=0.5)
        passos_var = tk.IntVar(value=7)
        modo_var   = tk.StringVar(value="LAB")
        _cache     = {}

        # ── Funções de interpolação ──────────────────────────────────────────

        def interp_lab(ha, hb, t):
            la = xyz_to_lab(rgb_to_xyz(hex_to_rgb(ha)))
            lb = xyz_to_lab(rgb_to_xyz(hex_to_rgb(hb)))
            lm = tuple(la[j] + (lb[j] - la[j]) * t for j in range(3))
            return rgb_to_hex(xyz_to_rgb(lab_to_xyz(lm)))

        def interp_lch(ha, hb, t):
            la = lab_to_lch(xyz_to_lab(rgb_to_xyz(hex_to_rgb(ha))))
            lb = lab_to_lch(xyz_to_lab(rgb_to_xyz(hex_to_rgb(hb))))
            L  = la[0] + (lb[0] - la[0]) * t
            C  = la[1] + (lb[1] - la[1]) * t
            dH = lb[2] - la[2]
            if dH >  180: dH -= 360
            if dH < -180: dH += 360
            H  = (la[2] + dH * t) % 360
            return lch_para_hex((L, C, H))

        def interp_rgb(ha, hb, t):
            ra, ga, ba = hex_to_rgb(ha)
            rb, gb, bb = hex_to_rgb(hb)
            return rgb_to_hex([ra+(rb-ra)*t, ga+(gb-ga)*t, ba+(bb-ba)*t])

        _interp_fn = {"LAB": interp_lab, "LCH": interp_lch, "RGB": interp_rgb}

        def gerar_escala(ha, hb, n, modo):
            fn = _interp_fn[modo]
            return [fn(ha, hb, i / max(n-1, 1)) for i in range(n)]

        # ── Renderização (definida antes da UI para que os widgets possam referenciá-la) ──

        # Estes labels/canvas serão atribuídos abaixo e usados aqui via closure
        _refs = {}  # guarda referências mutáveis aos widgets criados depois

        def desenhar_gradiente_mixer(cores):
            cv = _refs.get("canvas_grad")
            if not cv or not cores:
                return
            cv.update_idletasks()
            cw, ch = cv.winfo_width(), 70
            if cw < 2:
                return
            cv.delete("all")
            lf = cw / len(cores)
            for idx, cor in enumerate(cores):
                try:
                    cv.create_rectangle(idx*lf, 0, (idx+1)*lf, ch, fill=cor, outline=cor)
                    if lf > 46:
                        cv.create_text(idx*lf + lf/2, ch/2,
                                       text=cor.upper(),
                                       fill=cor_texto_contraste(cor),
                                       font=("Courier", 7, "bold"))
                except Exception:
                    pass

        def desenhar_swatches_mixer(cores):
            fs = _refs.get("frame_swatches")
            if not fs:
                return
            for w in fs.winfo_children():
                w.destroy()
            row = tk.Frame(fs, bg=BG)
            row.pack(fill=tk.X)
            for cor in cores:
                try:
                    f = tk.Frame(row, bg=BG)
                    f.pack(side=tk.LEFT, padx=3)
                    sw = tk.Label(f, bg=cor, width=4, height=2,
                                  relief=tk.FLAT, cursor="hand2")
                    sw.pack()
                    tk.Label(f, text=cor.upper(), bg=BG, fg=FG,
                             font=("Courier", 7)).pack()

                    def copiar(c=cor):
                        win.clipboard_clear()
                        win.clipboard_append(c)
                        self.label_info.config(text=f"Copiado: {c}", fg="#2196f3")

                    sw.bind("<Button-1>", lambda e, c=cor: copiar(c))
                    sw.bind("<Double-Button-1>",
                            lambda e, c=cor: [self.gerar_lista_cores(c), win.destroy()])
                except Exception:
                    pass

        def atualizar(*_):
            ha = cor_a_var.get().strip()
            hb = cor_b_var.get().strip()
            if not ha.startswith("#"): ha = "#" + ha
            if not hb.startswith("#"): hb = "#" + hb
            ha, hb = ha[:7], hb[:7]
            try:
                hex_to_rgb(ha)
                hex_to_rgb(hb)
            except Exception:
                return

            t    = t_var.get()
            modo = modo_var.get()
            n    = passos_var.get()

            fn    = _interp_fn[modo]
            cor_t = fn(ha, hb, t)
            _cache["cor_t"] = cor_t

            escala = gerar_escala(ha, hb, n, modo)
            _cache["escala"] = escala

            lbl = _refs.get("lbl_t_hex")
            prt = _refs.get("prev_t")
            if lbl:
                try: lbl.config(text=cor_t.upper())
                except Exception: pass
            if prt:
                try: prt.config(bg=cor_t)
                except Exception: pass

            desenhar_gradiente_mixer(escala)
            desenhar_swatches_mixer(escala)

        self._mixer_updater = atualizar

        # ── UI — construída DEPOIS de atualizar estar definida ────────────────

        # Seleção de cores A e B
        frame_cores = tk.Frame(win, bg=BG, pady=12)
        frame_cores.pack(fill=tk.X, padx=20)

        def bloco_cor(parent, var, rotulo):
            f = tk.Frame(parent, bg=BG)
            f.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=8)
            tk.Label(f, text=rotulo, bg=BG, fg=FG,
                     font=("Arial", 10, "bold")).pack(anchor=tk.W)
            linha = tk.Frame(f, bg=BG)
            linha.pack(fill=tk.X, pady=4)

            entry = tk.Entry(linha, textvariable=var, width=9, font=("Courier", 11))
            entry.pack(side=tk.LEFT)

            prev_lbl = tk.Label(linha, width=3, height=1, bg=var.get(), relief=tk.FLAT)
            prev_lbl.pack(side=tk.LEFT, padx=6)

            def pick_seletor():
                c = colorchooser.askcolor(title=f"Escolher {rotulo}",
                                          color=var.get(), parent=win)[1]
                if c:
                    var.set(c)
                    atualizar()

            def pick_historico():
                if not self.historico_cores:
                    return
                pop = tk.Toplevel(win)
                pop.title("Histórico")
                pop.attributes("-topmost", True)
                pop.config(bg=BG)
                pop.geometry("240x70")
                for cor in self.historico_cores[:10]:
                    tk.Button(
                        pop, bg=cor, width=2, height=1,
                        relief=tk.FLAT, cursor="hand2",
                        command=lambda c=cor: [var.set(c), pop.destroy(), atualizar()]
                    ).pack(side=tk.LEFT, padx=2, pady=12)

            def pick_gotas():
                win.withdraw()
                t_name = "mixer_a" if rotulo == "Cor A" else "mixer_b"
                self.ferramenta_conta_gotas(target=t_name)

            tk.Button(linha, text="🎨", bg=BTN, fg=FG,
                      relief=tk.FLAT, command=pick_seletor).pack(side=tk.LEFT, padx=2)
            tk.Button(linha, text="🧪", bg=BTN, fg=FG,
                      relief=tk.FLAT, command=pick_gotas).pack(side=tk.LEFT, padx=2)
            tk.Button(linha, text="🕐", bg=BTN, fg=FG,
                      relief=tk.FLAT, command=pick_historico).pack(side=tk.LEFT, padx=2)

            def on_entry(*_):
                val = var.get().strip()
                if not val.startswith("#"): val = "#" + val
                val = val[:7]
                try:
                    hex_to_rgb(val)
                    var.set(val)
                    prev_lbl.config(bg=val)
                    atualizar()
                except Exception:
                    pass

            entry.bind("<Return>",   on_entry)
            entry.bind("<FocusOut>", on_entry)
            var.trace_add("write", lambda *_: (
                prev_lbl.config(bg=var.get())
                if var.get().startswith("#") and len(var.get()) == 7 else None
            ))

        bloco_cor(frame_cores, cor_a_var, "Cor A")
        bloco_cor(frame_cores, cor_b_var, "Cor B")

        # Modo de interpolação
        frame_modo = tk.Frame(win, bg=BG)
        frame_modo.pack(fill=tk.X, padx=20, pady=(0, 4))
        tk.Label(frame_modo, text="Modo:", bg=BG, fg=FG,
                 font=("Arial", 9, "bold")).pack(side=tk.LEFT, padx=(0, 8))
        for m in ("LAB", "LCH", "RGB"):
            tk.Radiobutton(frame_modo, text=m, variable=modo_var, value=m,
                           bg=BG, fg=FG, selectcolor=BG,
                           font=("Arial", 9),
                           command=atualizar).pack(side=tk.LEFT, padx=8)
        tk.Label(frame_modo,
                 text="LAB = luminosidade uniforme  ·  LCH = matiz suave  ·  RGB = linear",
                 bg=BG, fg="#888888", font=("Arial", 7, "italic")).pack(side=tk.LEFT, padx=10)

        # Slider t
        frame_t = tk.Frame(win, bg=BG)
        frame_t.pack(fill=tk.X, padx=20, pady=4)
        tk.Label(frame_t, text="Mistura (t):", bg=BG, fg=FG,
                 font=("Arial", 9)).pack(side=tk.LEFT)
        tk.Scale(frame_t, from_=0.0, to=1.0, resolution=0.01,
                 orient=tk.HORIZONTAL, variable=t_var,
                 bg=BG, fg=FG, highlightthickness=0,
                 troughcolor=p["canvas"], length=320,
                 command=lambda _: atualizar()).pack(side=tk.LEFT, padx=6)
        lbl_t_hex = tk.Label(frame_t, text="", bg=BG, fg=FG,
                             font=("Courier", 10, "bold"), width=8)
        lbl_t_hex.pack(side=tk.LEFT, padx=4)
        prev_t = tk.Label(frame_t, width=3, height=1, bg=BG, relief=tk.FLAT)
        prev_t.pack(side=tk.LEFT, padx=4)
        _refs["lbl_t_hex"] = lbl_t_hex
        _refs["prev_t"]    = prev_t

        # Slider de passos
        frame_passos = tk.Frame(win, bg=BG)
        frame_passos.pack(fill=tk.X, padx=20, pady=4)
        tk.Label(frame_passos, text="Passos na escala:", bg=BG, fg=FG,
                 font=("Arial", 9)).pack(side=tk.LEFT)
        tk.Scale(frame_passos, from_=2, to=20,
                 orient=tk.HORIZONTAL, variable=passos_var,
                 bg=BG, fg=FG, highlightthickness=0,
                 troughcolor=p["canvas"], length=200,
                 command=lambda _: atualizar()).pack(side=tk.LEFT, padx=6)

        # Canvas de gradiente
        frame_grad = tk.Frame(win, bg=BG)
        frame_grad.pack(fill=tk.X, padx=20, pady=6)
        tk.Label(frame_grad, text="Escala interpolada:", bg=BG, fg=FG,
                 font=("Arial", 9, "bold")).pack(anchor=tk.W)
        canvas_grad = tk.Canvas(frame_grad, height=70, bg=p["canvas"],
                                highlightthickness=1, highlightbackground=BTN)
        canvas_grad.pack(fill=tk.X, pady=4)
        _refs["canvas_grad"] = canvas_grad
        canvas_grad.bind("<Configure>", lambda e: atualizar())

        # Swatches
        frame_swatches = tk.Frame(win, bg=BG)
        frame_swatches.pack(fill=tk.X, padx=20)
        _refs["frame_swatches"] = frame_swatches

        # Botões de ação
        frame_acoes = tk.Frame(win, bg=BG, pady=10)
        frame_acoes.pack(fill=tk.X, padx=20)

        def usar_cor_t():
            cor = _cache.get("cor_t")
            if cor:
                self.salvar_estado(f"Mixer: cor t={t_var.get():.2f}")
                self.gerar_lista_cores(cor, salvar_estado_undo=False)
                self.label_info.config(
                    text=f"Mixer → {cor.upper()}  t={t_var.get():.2f}  {modo_var.get()}",
                    fg="#6a1b9a")
                win.destroy()

        def usar_escala():
            cores = _cache.get("escala", [])
            if cores:
                self.salvar_estado(f"Mixer: escala {modo_var.get()}")
                self.cores_hex = cores
                self.cor_atual = cores[len(cores) // 2]
                self.adicionar_historico(self.cor_atual)
                self.atualizar_label_info()
                self.desenhar_gradiente()
                self.label_info.config(
                    text=f"Mixer → escala {modo_var.get()}  {len(cores)} passos",
                    fg="#2e7d32")
                win.destroy()

        def usar_como_gradiente():
            ha, hb = cor_a_var.get(), cor_b_var.get()
            try:
                hex_to_rgb(ha); hex_to_rgb(hb)
            except Exception:
                return
            self.salvar_estado(f"Mixer: gradiente {ha} → {hb}")
            lab_a = xyz_to_lab(rgb_to_xyz(hex_to_rgb(ha)))
            lab_b = xyz_to_lab(rgb_to_xyz(hex_to_rgb(hb)))
            dist  = delta_e_cie76(lab_a, lab_b)
            n     = max(4, int(dist / self.passo_delta.get()))
            cores = [interp_lab(ha, hb, i / max(n-1, 1)) for i in range(n)]
            self.cores_hex = cores
            self.cor_atual = ha
            self.adicionar_historico(ha)
            self.atualizar_label_info()
            self.desenhar_gradiente()
            self.label_info.config(
                text=f"Mixer → gradiente perceptual  {len(cores)} passos",
                fg="#1565c0")
            win.destroy()

        def trocar_cores():
            a, b = cor_a_var.get(), cor_b_var.get()
            cor_a_var.set(b); cor_b_var.set(a)
            atualizar()

        tk.Button(frame_acoes, text="⇄ Trocar A↔B",
                  command=trocar_cores, bg=BTN, fg=FG,
                  relief=tk.FLAT, padx=6).pack(side=tk.LEFT, padx=4)
        tk.Button(frame_acoes, text="✅ Usar cor em t",
                  command=usar_cor_t,
                  bg="#c8e6c9", fg="#1b5e20",
                  font=("Arial", 9, "bold"), relief=tk.FLAT, padx=8).pack(side=tk.LEFT, padx=4)
        tk.Button(frame_acoes, text="🎨 Usar escala",
                  command=usar_escala,
                  bg="#e1bee7", fg="#4a148c",
                  font=("Arial", 9, "bold"), relief=tk.FLAT, padx=8).pack(side=tk.LEFT, padx=4)
        tk.Button(frame_acoes, text="🌈 Gradiente suave A→B",
                  command=usar_como_gradiente,
                  bg="#bbdefb", fg="#0d47a1",
                  font=("Arial", 9, "bold"), relief=tk.FLAT, padx=8).pack(side=tk.LEFT, padx=4)
        tk.Button(frame_acoes, text="✖ Fechar",
                  command=win.destroy, bg=BTN, fg=FG,
                  relief=tk.FLAT, padx=8).pack(side=tk.RIGHT, padx=4)

        # Primeiro render após a janela estar visível
        win.after(80, atualizar)

    # FERRAMENTAS 
    def ferramenta_conta_gotas(self, target=None):
        self.root.withdraw(); time.sleep(0.2); print_tela = pyautogui.screenshot(); larg_t, alt_t = print_tela.size
        overlay = tk.Toplevel(); overlay.attributes("-fullscreen", True, "-topmost", True); overlay.config(cursor="tcross") 
        canvas_ov = tk.Canvas(overlay, highlightthickness=0); canvas_ov.pack(fill="both", expand=True)
        img_bg = ImageTk.PhotoImage(print_tela); canvas_ov.create_image(0, 0, anchor="nw", image=img_bg)
        lupa_size, zoom = 180, 10; mask = Image.new('L', (lupa_size, lupa_size), 0); ImageDraw.Draw(mask).ellipse((0, 0, lupa_size, lupa_size), fill=255)
        def atualizar_lupa(event):
            x, y = event.x, event.y; raio = (lupa_size // zoom) // 2; box = (x - raio, y - raio, x + raio, y + raio); recorte = print_tela.crop(box)
            zoom_img = recorte.resize((lupa_size, lupa_size), Image.NEAREST).convert("RGBA"); zoom_img.putalpha(mask)
            draw = ImageDraw.Draw(zoom_img); meio = lupa_size // 2; draw.line([meio, 0, meio, lupa_size], fill="red", width=1); draw.line([0, meio, lupa_size, meio], fill="red", width=1)
            px_color = print_tela.getpixel((x, y)); draw.rectangle([meio-30, meio+20, meio+30, meio+40], fill="white", outline="black"); draw.text((meio-22, meio+24), rgb_to_hex(px_color), fill="black")
            img_lupa = ImageTk.PhotoImage(zoom_img); canvas_ov.delete("lupa_dinamica")
            nx = x + 30 if x + lupa_size + 30 < larg_t else x - lupa_size - 30; ny = y + 30 if y + lupa_size + 30 < alt_t else y - lupa_size - 30
            canvas_ov.create_image(nx, ny, anchor="nw", image=img_lupa, tag="lupa_dinamica"); canvas_ov.create_oval(nx, ny, nx+lupa_size, ny+lupa_size, outline="black", width=2, tag="lupa_dinamica"); canvas_ov.img_ref = img_lupa
        def capturar(event):
            c = rgb_to_hex(print_tela.getpixel((event.x, event.y))); overlay.destroy(); self.root.deiconify()
            if target == "mixer_a" and hasattr(self, '_mixer_cor_a_var'):
                self._mixer_cor_a_var.set(c)
                if hasattr(self, '_mixer_updater'): self._mixer_updater()
                if hasattr(self, '_mixer_win'): self._mixer_win.deiconify()
            elif target == "mixer_b" and hasattr(self, '_mixer_cor_b_var'):
                self._mixer_cor_b_var.set(c)
                if hasattr(self, '_mixer_updater'): self._mixer_updater()
                if hasattr(self, '_mixer_win'): self._mixer_win.deiconify()
            else:
                self.gerar_lista_cores(c, salvar_estado_undo=True); self.salvar_configuracoes()
        canvas_ov.bind("<Motion>", atualizar_lupa); canvas_ov.bind("<Button-1>", capturar)
        
        def on_escape(e):
            overlay.destroy()
            self.root.deiconify()
            if target in ["mixer_a", "mixer_b"] and hasattr(self, '_mixer_win'):
                self._mixer_win.deiconify()
        overlay.bind("<Escape>", on_escape); overlay.img_ref = img_bg

    def aplicar_tema(self, event=None):
        p = self.paletas[self.tema.get()]; self.root.config(bg=p["window_bg"]); self.frame_menu.config(bg=p["window_bg"]); self.canvas.config(bg=p["canvas"])
        self.atualizar_label_info()
        self.label_info.config(bg=p["window_bg"])
        self.frame_principal.config(bg=p["window_bg"])
        self.frame_historico.config(bg=p["window_bg"])

        # Atualiza botões do menu
        for w in self.frame_menu.winfo_children():
            if isinstance(w, tk.Button): w.config(bg=p["btn"] if w.cget("text") != "🧪 Conta-Gotas" else p["special"], fg=p["text_fg"])

        # Atualiza painel de projetos
        self.criar_ui_painel_projetos()

        if self.config_win and tk.Toplevel.winfo_exists(self.config_win):
            self.config_win.config(bg=p["window_bg"]); self.config_container.config(bg=p["window_bg"])
            def upd(parent):
                for c in parent.winfo_children():
                    if isinstance(c, (tk.Label, tk.Radiobutton, tk.Scale, tk.Frame)):
                        try: c.config(bg=p["window_bg"], fg=p["text_fg"])
                        except: pass
                    if isinstance(c, tk.Button) and c.cget("text") != "🔄 Restaurar Padrões": c.config(bg=p["btn"], fg=p["text_fg"])
                    upd(c)
            upd(self.config_win)
        if self.cores_hex: self.desenhar_gradiente()

    # RENDERIZAÇÃO TEMPO REAL
    def desenhar_gradiente(self):
        if not self.cores_hex: return
        self.canvas.delete("all")
        w = self.canvas.winfo_width()
        h = self.canvas.winfo_height()
        if w <= 1: w = 760
        if h <= 1: h = 400
            
        larg_f = w / len(self.cores_hex)
        # Cache de valores para performance
        bright = self.adj_bright.get()
        contrast = self.adj_contrast.get()
        gamma = self.adj_gamma.get()
        sat_val = self.adj_sat.get()
        hue_val = self.adj_hue.get()
        temp_val = self.adj_temp.get()
        daltonismo = self.sim_daltonismo.get()
        tr, tg, tb = kelvin_to_rgb(temp_val)

        for i, c in enumerate(self.cores_hex):
            rgb = hex_to_rgb(c)
            r, g, b = [v/255.0 for v in rgb]
            # Temperatura
            r, g, b = r*tr, g*tg, b*tb
            # HSL
            hue, l, sat = colorsys.rgb_to_hls(r, g, b)
            r, g, b = colorsys.hls_to_rgb((hue + hue_val/360.0)%1.0, l, max(0, min(1, sat*sat_val)))
            # Gamma
            r, g, b = [pow(v, gamma) for v in [r, g, b]]
            # Contraste/Brilho
            r, g, b = [(v-0.5)*contrast + 0.5 + (bright/255.0) for v in [r, g, b]]
            # Simulação
            rgb_sim = simular_daltonismo([max(0, min(1, v)) for v in [r, g, b]], daltonismo)
            hex_f = rgb_to_hex([v*255 for v in rgb_sim])
            self.canvas.create_rectangle(i*larg_f, 0, (i+1)*larg_f, h, fill=hex_f, outline=hex_f)
            # Preview de contraste - mostra "Aa" na cor de texto adequada
            # Limita a quantidade de textos para não poluir quando há poucas cores
            max_previews = 8  # Máximo de previews "Aa" a mostrar
            if self.mostrar_preview_contraste.get() and larg_f > 30 and len(self.cores_hex) <= max_previews:
                txt_cor = cor_texto_contraste(hex_f)
                cx = i * larg_f + larg_f / 2
                cy = h / 2
                self.canvas.create_text(cx, cy, text="Aa", fill=txt_cor, font=("Arial", 10, "bold"))

            # ── Badge WCAG ──────────────────────────────────────────────────
            if self.mostrar_wcag.get() and larg_f > 44:
                cx = i * larg_f + larg_f / 2
                fundo = self.wcag_fundo_var.get()

                if fundo == "preto_branco":
                    # Mostra o melhor nível atingido contra preto ou branco
                    r_branco = razao_contraste(hex_f, "#ffffff")
                    r_preto  = razao_contraste(hex_f, "#000000")
                    melhor_r = max(r_branco, r_preto)
                    nivel    = nivel_wcag(melhor_r)
                    rotulo   = f"{nivel}  {melhor_r:.1f}:1"
                elif fundo == "branco":
                    r = razao_contraste(hex_f, "#ffffff")
                    nivel  = nivel_wcag(r)
                    rotulo = f"{nivel}  {r:.1f}:1"
                elif fundo == "preto":
                    r = razao_contraste(hex_f, "#000000")
                    nivel  = nivel_wcag(r)
                    rotulo = f"{nivel}  {r:.1f}:1"
                else:
                    # Fundo customizado salvo
                    r = razao_contraste(hex_f, fundo)
                    nivel  = nivel_wcag(r)
                    rotulo = f"{nivel}  {r:.1f}:1"

                cores_badge = _WCAG_CORES.get(nivel, _WCAG_CORES["Falha"])
                pad_x, pad_y = 5, 3
                txt_w  = max(60, len(rotulo) * 7)
                txt_h  = 16
                bx     = cx - txt_w / 2
                by     = h - 28
                # Fundo do badge (retângulo arredondado simulado com dois rects + oval)
                self.canvas.create_rectangle(
                    bx, by, bx + txt_w, by + txt_h,
                    fill=cores_badge["bg"], outline="", width=0)
                self.canvas.create_text(
                    cx, by + txt_h / 2,
                    text=rotulo, fill=cores_badge["fg"],
                    font=("Arial", 8, "bold"), anchor="center")

    def adicionar_historico(self, cor):
        if cor in self.historico_cores:
            self.historico_cores.remove(cor)
        self.historico_cores.insert(0, cor)
        self.historico_cores = self.historico_cores[:10]
        self.atualizar_ui_historico()

    def atualizar_ui_historico(self):
        for w in self.frame_historico.winfo_children(): w.destroy()
        p = self.paletas[self.tema.get()]
        tk.Label(self.frame_historico, text="Recentes", bg=p["window_bg"], fg=p["text_fg"], font=("Arial", 9, "bold")).pack(pady=5)
        for cor in self.historico_cores:
            btn = tk.Button(self.frame_historico, bg=cor, width=3, height=1, relief=tk.FLAT, cursor="hand2",
                           command=lambda c=cor: [self.salvar_estado(f"Selecionar do histórico: {c}"), self.gerar_lista_cores(c, salvar_estado_undo=False)])
            btn.pack(pady=2)

    def gerar_lista_cores(self, hex_base, salvar_estado_undo=True):
        # Salva estado anterior se necessário
        if salvar_estado_undo:
            self.salvar_estado(f"Gerar paleta de {hex_base}")

        self.cor_atual = hex_base
        self.adicionar_historico(hex_base)
        self.atualizar_label_info()
        try:
            lab_alvo = xyz_to_lab(rgb_to_xyz(hex_to_rgb(hex_base))); pontos = [(0,0,0), lab_alvo, (100,0,0)]; self.cores_hex = []
            for i in range(len(pontos)-1):
                ini, fim = pontos[i], pontos[i+1]; dist = delta_e_cie76(ini, fim); passos = max(2, int(dist / self.passo_delta.get()))
                for p in range(passos):
                    t = p / (passos - 1) if passos > 1 else 0; curr = tuple(ini[j] + (fim[j]-ini[j])*t for j in range(3)); self.cores_hex.append(rgb_to_hex(xyz_to_rgb(lab_to_xyz(curr))))
            self.desenhar_gradiente()
        except Exception as e:
            print(f"Erro ao gerar lista de cores: {e}")

    def atualizar_label_info(self):
        """Atualiza o label de info com a cor atual"""
        p = self.paletas[self.tema.get()]
        self.label_info.config(text=f"Color Lab Pro v4.6 | Base: {self.cor_atual}", fg=p["text_fg"])

    def ferramenta_digitar(self):
        cor = simpledialog.askstring("Input", "HEX:", parent=self.root)
        if cor:
            self.salvar_estado("Inserir HEX manualmente")
            self.gerar_lista_cores('#' + cor.lstrip('#'), salvar_estado_undo=False)

    def ferramenta_seletor(self):
        cor = colorchooser.askcolor(title="Seletor")[1]
        if cor:
            self.salvar_estado("Selecionar cor")
            self.gerar_lista_cores(cor, salvar_estado_undo=False)

    def exportar_paleta(self):
        if not self.cores_hex:
            messagebox.showinfo("Exportar", "Nenhuma cor para exportar.", parent=self.root)
            return
        from tkinter import filedialog
        tipos = [
            ("Adobe ASE (*.ase)", "*.ase"),
            ("GIMP Palette (*.gpl)", "*.gpl"),
            ("CSS (*.css)", "*.css"),
            ("SCSS Map (*.scss)", "*.scss"),
            ("Tailwind Config (*.config.js)", "*.config.js"),
            ("JSON (*.json)", "*.json"),
            ("W3C Design Tokens (*.tokens.json)", "*.tokens.json"),
            ("Texto (*.txt)", "*.txt"),
            ("PNG Image (*.png)", "*.png"),
            ("JPEG Image (*.jpg)", "*.jpg"),
            ("Todos (*)", "*.*")
        ]
        arquivo = filedialog.asksaveasfilename(filetypes=tipos, title="Exportar Paleta")
        if not arquivo: return

        # Normaliza separadores de caminho e detecta extensão
        arquivo = os.path.normpath(arquivo)
        arquivo_lower = arquivo.lower()

        # Detecta extensão especial .config.js primeiro (antes do splitext)
        if arquivo_lower.endswith(".config.js"):
            ext = ".config.js"
        elif arquivo_lower.endswith(".tokens.json"):
            ext = ".tokens.json"
        else:
            # Se não tiver extensão reconhecida, assume baseado na extensão atual
            ext = os.path.splitext(arquivo)[1].lower()
            # Fallback: se não tiver extensão, adiciona .ase
            if not ext:
                ext = ".ase"
                arquivo = arquivo + ext

        try:
            if ext == ".css":
                with open(arquivo, "w") as f:
                    f.write(":root {\n")
                    for i, c in enumerate(self.cores_hex):
                        f.write(f"  --color-{i+1}: {c};\n")
                    f.write("}\n")
            elif ext == ".scss":
                with open(arquivo, "w") as f:
                    f.write("// Color Lab Pro - SCSS Color Map\n\n")
                    f.write("$colors: (\n")
                    for i, c in enumerate(self.cores_hex):
                        f.write(f'  "color-{i+1}": {c},\n')
                    f.write(");\n\n")
                    for i, c in enumerate(self.cores_hex):
                        f.write(f"$color-{i+1}: {c};\n")
            elif ext == ".config.js":
                with open(arquivo, "w") as f:
                    f.write("// Color Lab Pro - Tailwind Config\n")
                    f.write("// Para usar: const colors = require('./{0}').colors;\n".format(os.path.basename(arquivo)))
                    f.write("// Ou importe no tailwind.config.js: const colors = require('./{0}');\n\n".format(os.path.basename(arquivo)))
                    f.write("module.exports = {\n")
                    f.write("  colors: {\n")
                    for i, c in enumerate(self.cores_hex):
                        f.write(f'    "color-{i+1}": "{c}",\n')
                    f.write("  },\n")
                    f.write("  theme: {\n")
                    f.write("    extend: {\n")
                    f.write("      colors: {\n")
                    for i, c in enumerate(self.cores_hex):
                        nome_base = os.path.splitext(os.path.basename(arquivo))[0].replace('.config', '').replace('.', '-')
                        f.write(f'        "{nome_base}-{i+1}": "{c}",\n')
                    f.write("      },\n")
                    f.write("    },\n")
                    f.write("  },\n")
                    f.write("};\n")
            elif ext == ".json":
                with open(arquivo, "w") as f:
                    json.dump({"colors": self.cores_hex, "base": self.cor_atual}, f, indent=2)
            elif ext == ".tokens.json":
                dt_now = datetime.now().isoformat()
                tokens = {
                    "$schema": "https://design-tokens.github.io/community-group/format/dtcg-format.format.json",
                    "$version": "1.0.0",
                    "$timestamp": dt_now,
                    "colors": {}
                }
                for i, c in enumerate(self.cores_hex):
                    tokens["colors"][f"color-{i+1}"] = {
                        "$type": "color",
                        "$value": c,
                        "$description": f"Cor {i+1} gerada a partir de {self.cor_atual}"
                    }
                with open(arquivo, "w") as f:
                    json.dump(tokens, f, indent=2)
            elif ext == ".txt":
                with open(arquivo, "w") as f:
                    for c in self.cores_hex:
                        f.write(f"{c}\n")
            elif ext == ".ase":
                self.exportar_ase(arquivo, self.cores_hex)
            elif ext == ".gpl":
                self.exportar_gpl(arquivo, self.cores_hex)
            elif ext in (".png", ".jpg", ".jpeg"):
                formato = "jpeg" if ext in (".jpg", ".jpeg") else "png"
                self.exportar_imagem_paleta(arquivo, self.cores_hex, formato)
            self.label_info.config(text=f"Exportado: {os.path.basename(arquivo)}", fg="#2e7d32")
        except Exception as e:
            messagebox.showerror("Erro", f"Falha ao exportar: {e}", parent=self.root)

    def importar_imagem(self):
        from tkinter import filedialog
        # Formatos suportados - populares e de aplicativos de design
        tipos = [
            ("Todos os suportados", "*.png;*.jpg;*.jpeg;*.bmp;*.tiff;*.tif;*.webp;*.gif;*.ico;*.ppm;*.pgm;*.pbm"),
            ("PNG", "*.png"),
            ("JPEG/JPG", "*.jpg;*.jpeg"),
            ("BMP", "*.bmp"),
            ("TIFF", "*.tiff;*.tif"),
            ("WebP", "*.webp"),
            ("GIF", "*.gif"),
            ("ICO", "*.ico"),
            ("PPM/PGM/PBM", "*.ppm;*.pgm;*.pbm"),
            ("Todos (*)", "*.*")
        ]
        arquivo = filedialog.askopenfilename(filetypes=tipos, title="Importar Imagem")
        if not arquivo:
            return

        # Diálogo para escolher método e número de cores
        self.mostrar_dialogo_importacao(arquivo)

    def mostrar_dialogo_importacao(self, arquivo):
        """Mostra diálogo para configurar importação"""
        dialog = tk.Toplevel(self.root)
        dialog.title("Importar Cores da Imagem")
        dialog.geometry("400x300")
        dialog.transient(self.root)
        dialog.grab_set()

        # Variáveis
        num_cores_var = tk.IntVar(value=8)
        metodo_var = tk.StringVar(value="kmeans" if SKLEARN_AVAILABLE else "quantizacao")

        # Frame principal
        frame = tk.Frame(dialog, padx=20, pady=20)
        frame.pack(fill=tk.BOTH, expand=True)

        tk.Label(frame, text="Configuração de Extração de Cores", font=("Arial", 11, "bold")).pack(pady=(0, 15))

        # Número de cores
        tk.Label(frame, text="Número de cores:").pack(anchor=tk.W)
        tk.Scale(frame, from_=2, to=16, orient=tk.HORIZONTAL, variable=num_cores_var).pack(fill=tk.X, pady=(0, 15))

        # Método
        tk.Label(frame, text="Método de extração:").pack(anchor=tk.W)

        kmeans_radio = tk.Radiobutton(frame, text="K-Means Clustering (mais preciso)",
                                     variable=metodo_var, value="kmeans")
        kmeans_radio.pack(anchor=tk.W)

        if not SKLEARN_AVAILABLE:
            kmeans_radio.config(state=tk.DISABLED)
            tk.Label(frame, text="(Instale scikit-learn para usar K-Means)",
                    fg="gray", font=("Arial", 8)).pack(anchor=tk.W)

        tk.Radiobutton(frame, text="Quantização de Cores (mais rápido)",
                      variable=metodo_var, value="quantizacao").pack(anchor=tk.W)

        # Botões
        btn_frame = tk.Frame(frame)
        btn_frame.pack(fill=tk.X, pady=(20, 0))

        def processar():
            dialog.destroy()
            self.processar_importacao(arquivo, num_cores_var.get(), metodo_var.get())

        def cancelar():
            dialog.destroy()

        tk.Button(btn_frame, text="Cancelar", command=cancelar).pack(side=tk.LEFT, padx=5)
        tk.Button(btn_frame, text="Importar", command=processar, bg="#2196f3", fg="white").pack(side=tk.RIGHT, padx=5)

    def processar_importacao(self, arquivo, num_cores, metodo):
        """Processa a importação da imagem com as configurações escolhidas"""
        try:
            img = Image.open(arquivo)
            # Converte para RGB se necessário
            if img.mode in ('RGBA', 'P', 'LA', 'L'):
                img = img.convert('RGB')

            # Extrai cores conforme o método escolhido
            if metodo == "kmeans" and SKLEARN_AVAILABLE:
                cores_dominantes = self.extrair_cores_kmeans(img, num_cores)
            else:
                cores_dominantes = self.extrair_cores_quantizacao(img, num_cores)

            if cores_dominantes:
                self.salvar_estado(f"Importar: {os.path.basename(arquivo)}")
                self.cores_hex = cores_dominantes
                self.cor_atual = cores_dominantes[len(cores_dominantes)//2]  # Cor do meio
                self.desenhar_gradiente()
                self.label_info.config(text=f"Importado: {os.path.basename(arquivo)} ({len(cores_dominantes)} cores)", fg="#2e7d32")
            else:
                messagebox.showinfo("Importar", "Não foi possível extrair cores da imagem.", parent=self.root)
        except Exception as e:
            messagebox.showerror("Erro", f"Falha ao importar imagem: {e}", parent=self.root)

    def exportar_ase(self, filepath, cores):
        """Exporta para Adobe Swatch Exchange format (binário)"""
        def write_string_utf16_be(s):
            """Converte string para UTF-16 BE com null terminator"""
            encoded = s.encode('utf-16-be') + b'\x00\x00'
            return struct.pack('>H', len(s) + 1) + encoded

        def write_color_block(color_hex, index):
            """Cria um bloco de cor ASE"""
            r, g, b = hex_to_rgb(color_hex)
            # Normaliza para 0-1
            r_norm, g_norm, b_norm = r/255.0, g/255.0, b/255.0

            # Nome da cor
            nome = f"Color {index+1}"
            nome_data = write_string_utf16_be(nome)

            # Modo de cor RGB (4 bytes + null)
            modo = b'RGB '

            # Valores float (4 bytes cada, big-endian)
            valores = struct.pack('>fff', r_norm, g_norm, b_norm)

            # Tipo de cor: 0 = global
            tipo_cor = struct.pack('>H', 0)

            # Conteúdo do bloco
            block_content = nome_data + modo + valores + tipo_cor

            # Header do bloco: tipo (0x0001 = cor) + tamanho
            block_header = struct.pack('>HH', 0x0001, len(block_content))

            return block_header + block_content

        with open(filepath, 'wb') as f:
            # Header ASEF
            f.write(b'ASEF')
            # Versão 1.0
            f.write(struct.pack('>HH', 1, 0))
            # Número de blocos
            f.write(struct.pack('>I', len(cores)))

            # Blocos de cor
            for i, cor in enumerate(cores):
                f.write(write_color_block(cor, i))

    def exportar_gpl(self, filepath, cores):
        """Exporta para GIMP Palette format"""
        with open(filepath, 'w') as f:
            f.write("GIMP Palette\n")
            f.write(f"Name: Color Lab Pro Export\n")
            f.write("Columns: 8\n")
            f.write("#\n")
            for i, cor in enumerate(cores):
                r, g, b = hex_to_rgb(cor)
                f.write(f"{r:3d} {g:3d} {b:3d}\tColor {i+1}\n")

    def exportar_imagem_paleta(self, filepath, cores, formato='png'):
        """Exporta paleta como imagem PNG/JPEG"""
        # Dimensões da imagem
        largura = 800
        altura_por_cor = 100
        altura = min(altura_por_cor * len(cores), 1200)  # Máximo 1200px
        cores_visiveis = min(len(cores), 12)  # Máximo 12 cores na imagem

        img = Image.new('RGB', (largura, altura_por_cor * cores_visiveis), '#ffffff')
        draw = ImageDraw.Draw(img)

        for i, cor in enumerate(cores[:cores_visiveis]):
            y_inicio = i * altura_por_cor
            y_fim = y_inicio + altura_por_cor

            # Desenha retângulo da cor
            draw.rectangle([0, y_inicio, largura, y_fim], fill=cor)

            # Texto com hex code
            text_color = cor_texto_contraste(cor)
            draw.text((20, y_inicio + 35), f"Color {i+1}: {cor.upper()}", fill=text_color, font=None)

        # Salva com qualidade alta para JPEG
        if formato.lower() in ('jpg', 'jpeg'):
            img = img.convert('RGB')
            img.save(filepath, 'JPEG', quality=95)
        else:
            img.save(filepath, 'PNG')

    def extrair_cores_kmeans(self, img, num_cores=8):
        """Extrai cores usando K-Means clustering"""
        if not SKLEARN_AVAILABLE:
            raise ImportError("scikit-learn não está instalado")

        # Reduz imagem para processamento
        img_small = img.copy()
        img_small.thumbnail((200, 200))

        # Converte para array numpy
        img_array = np.array(img_small)
        # Reshape para (pixels, 3 canais)
        pixels = img_array.reshape((-1, 3))

        # K-Means clustering
        kmeans = KMeans(n_clusters=num_cores, random_state=42, n_init=10)
        kmeans.fit(pixels)

        # Centroids (cores dominantes)
        cores = kmeans.cluster_centers_.astype(int)

        # Calcula frequência de cada cluster
        labels = kmeans.labels_
        frequencias = np.bincount(labels)

        # Ordena por frequência (mais comum primeiro)
        indices_ordenados = np.argsort(frequencias)[::-1]
        cores_ordenadas = cores[indices_ordenados]

        # Converte para hex
        return [rgb_to_hex(c) for c in cores_ordenadas]

    def extrair_cores_quantizacao(self, img, num_cores=8):
        """Extrai cores usando quantização PIL (método alternativo)"""
        # Usa o método quantize do PIL
        img_quantized = img.quantize(colors=num_cores, method=Image.Quantize.MEDIANCUT)

        # Obtém a paleta
        paleta = img_quantized.getpalette()

        # Extrai as cores
        cores = []
        for i in range(num_cores):
            r = paleta[i * 3]
            g = paleta[i * 3 + 1]
            b = paleta[i * 3 + 2]
            cores.append((r, g, b))

        return [rgb_to_hex(c) for c in cores]

    def copiar_clique(self, event):
        if not self.cores_hex: return
        w = self.canvas.winfo_width(); larg_f = w / len(self.cores_hex); idx = int(event.x // larg_f)
        if 0 <= idx < len(self.cores_hex):
            c = self.cores_hex[idx]; self.root.clipboard_clear(); self.root.clipboard_append(c); self.label_info.config(text=f"Copiado: {c}", fg="#2e7d32")

if __name__ == "__main__":
    root = tk.Tk(); app = AppCores(root); root.mainloop()