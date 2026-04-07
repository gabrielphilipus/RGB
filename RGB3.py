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
        self.ultima_atividade = ""  # Memória da última atividade realizada
        
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

        self.frame_menu = tk.Frame(self.root, pady=15)
        self.frame_menu.pack(side=tk.TOP, fill=tk.X)

        tk.Button(self.frame_menu, text="⌨️ HEX", command=self.ferramenta_digitar, width=12).pack(side=tk.LEFT, padx=10)
        tk.Button(self.frame_menu, text="🎨 Seletor", command=self.ferramenta_seletor, width=12).pack(side=tk.LEFT, padx=10)
        self.btn_gotas = tk.Button(self.frame_menu, text="🧪 Conta-Gotas", command=self.ferramenta_conta_gotas, width=12)
        self.btn_gotas.pack(side=tk.LEFT, padx=10)
        tk.Button(self.frame_menu, text="🎡 Harmonias", command=self.abrir_harmonias, width=12).pack(side=tk.LEFT, padx=10)
        tk.Button(self.frame_menu, text="📷 Importar", command=self.importar_imagem, width=12).pack(side=tk.LEFT, padx=10)
        tk.Button(self.frame_menu, text="💾 Exportar", command=self.exportar_paleta, width=12).pack(side=tk.LEFT, padx=10)
        tk.Button(self.frame_menu, text="⚙️ Config", command=self.abrir_configuracoes, width=12).pack(side=tk.RIGHT, padx=10)

        self.label_info = tk.Label(self.root, text=f"Color Lab Pro v4.6 | Base: {self.cor_atual}")
        self.label_info.pack()

        # Container principal: canvas + histórico
        self.frame_principal = tk.Frame(self.root)
        self.frame_principal.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)

        self.canvas = tk.Canvas(self.frame_principal, highlightthickness=0)
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # Painel de histórico
        self.frame_historico = tk.Frame(self.frame_principal, width=60)
        self.frame_historico.pack(side=tk.RIGHT, fill=tk.Y, padx=(10, 0))
        
        self.canvas.bind("<Configure>", lambda e: self.desenhar_gradiente())
        self.canvas.bind("<Button-1>", self.copiar_clique)

        self.root.protocol("WM_DELETE_WINDOW", self.ao_fechar)
        self.aplicar_tema()
        self.gerar_lista_cores(self.cor_atual)

        # Mostra mensagem de boas-vindas com memória da última atividade
        self.mostrar_memoria_inicial()

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
                    self.ultima_atividade = data.get("ultima_atividade", "")
                    self.cor_atual = data.get("ultima_cor", "#0078d7")
            except Exception as e:
                print(f"Erro ao carregar configurações: {e}")

    def ao_fechar(self):
        if self._debounce_timer:
            self.root.after_cancel(self._debounce_timer)
        self.ultima_atividade = f"Trabalhando com a paleta base {self.cor_atual}"
        self.salvar_configuracoes()
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
        tk.Checkbutton(self.config_container, text="Mostrar preview de contraste (Aa)", variable=self.mostrar_preview_contraste, command=self.desenhar_gradiente).pack(pady=5)
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

    # FERRAMENTAS 
    def ferramenta_conta_gotas(self):
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
            c = rgb_to_hex(print_tela.getpixel((event.x, event.y))); overlay.destroy(); self.root.deiconify(); self.gerar_lista_cores(c); self.salvar_configuracoes()
        canvas_ov.bind("<Motion>", atualizar_lupa); canvas_ov.bind("<Button-1>", capturar)
        overlay.bind("<Escape>", lambda e:[overlay.destroy(), self.root.deiconify()]); overlay.img_ref = img_bg

    def aplicar_tema(self, event=None):
        p = self.paletas[self.tema.get()]; self.root.config(bg=p["window_bg"]); self.frame_menu.config(bg=p["window_bg"]); self.canvas.config(bg=p["canvas"])
        self.atualizar_label_info()
        self.label_info.config(bg=p["window_bg"])
        self.frame_principal.config(bg=p["window_bg"])
        self.frame_historico.config(bg=p["window_bg"])
        for w in self.frame_menu.winfo_children():
            if isinstance(w, tk.Button): w.config(bg=p["btn"] if w.cget("text") != "🧪 Conta-Gotas" else p["special"], fg=p["text_fg"])
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
                           command=lambda c=cor: self.gerar_lista_cores(c))
            btn.pack(pady=2)

    def gerar_lista_cores(self, hex_base):
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
        if cor: self.gerar_lista_cores('#' + cor.lstrip('#'))

    def ferramenta_seletor(self):
        cor = colorchooser.askcolor(title="Seletor")[1]
        if cor: self.gerar_lista_cores(cor)

    def exportar_paleta(self):
        if not self.cores_hex:
            messagebox.showinfo("Exportar", "Nenhuma cor para exportar.", parent=self.root)
            return
        from tkinter import filedialog
        tipos = [
            ("Adobe ASE (*.ase)", "*.ase"),
            ("GIMP Palette (*.gpl)", "*.gpl"),
            ("CSS (*.css)", "*.css"),
            ("JSON (*.json)", "*.json"),
            ("Texto (*.txt)", "*.txt"),
            ("PNG Image (*.png)", "*.png"),
            ("JPEG Image (*.jpg)", "*.jpg"),
            ("Todos (*)", "*.*")
        ]
        arquivo = filedialog.asksaveasfilename(defaultextension=".ase", filetypes=tipos, title="Exportar Paleta")
        if not arquivo: return
        try:
            ext = os.path.splitext(arquivo)[1].lower()
            if ext == ".css":
                with open(arquivo, "w") as f:
                    f.write(":root {\n")
                    for i, c in enumerate(self.cores_hex):
                        f.write(f"  --color-{i+1}: {c};\n")
                    f.write("}\n")
            elif ext == ".json":
                with open(arquivo, "w") as f:
                    json.dump({"colors": self.cores_hex, "base": self.cor_atual}, f, indent=2)
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