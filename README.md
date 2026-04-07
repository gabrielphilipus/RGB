![Python](https://img.shields.io/badge/python-3670A0?style=for-the-badge&logo=python&logoColor=ffdd54)
![Windows](https://img.shields.io/badge/Windows-0078D6?style=for-the-badge&logo=windows&logoColor=white)

# 🧪 Color Lab Pro (v4.7)

**Color Lab Pro** é uma ferramenta avançada de análise cromática e geração de gradientes perceptuais, desenvolvida para profissionais de design e desenvolvedores que buscam precisão cirúrgica na manipulação de cores.

---

##  Funcionalidades Principais

###  Precisão Científica
Diferente de seletores comuns, este laboratório utiliza o espaço de cores **CIELAB** e a fórmula **Delta E (CIE76)** para calcular a diferença entre tons. Isso garante que os gradientes gerados sejam perfeitamente uniformes para a percepção humana.

###  Conta-Gotas e Lupa de Precisão
* **Magnifier 10x:** Captura qualquer pixel da tela com uma lupa circular.
* **Interpolação de Pixel:** Utiliza o método *Nearest Neighbor* totalmente ajustável para caso voce prefira com muito ou poucos pixels, sem desfoque artificial.

###  Reconhecimento de imagem 
* Utilizando algoritmos como K-Means Clustering e Quantização de Cores, para o melhor reconhecimento de cada pixel da imagem importada.

###  Simulação de Daltonismo (Acessibilidade)
Simulação em tempo real como a paleta de cores é vista por pessoas com diferentes tipos de deficiência visual:
* Deuteranopia e Protanopia (Vermelho-Verde).
* Tritanopia (Azul-Amarelo).
* Acromatopsia (Cegueira total de cores).

###  Ajustes Profissionais de Imagem
Controle total sobre o sinal da cor através de sliders de:
* Brilho, Contraste e Gamma.
* Saturação e Matiz (Hue).
* **Temperatura de Cor (Kelvin):** Simulação térmica de 1000K a 12000K.

---

##  Tecnologias Utilizadas
* **Linguagem:** Python
* **Interface Gráfica:** Tkinter
* **Processamento de Imagem:** Pillow (PIL)
* **Automação de Sistema:** PyAutoGUI
* **Matemática de Cores:** Colorsys e cálculos trigonométricos personalizados

---

##  Demonstração

![Interface Principal](assets/print_principal.png)

###  Conta-Gotas
![GIF da Lupa](assets/demonstracao_lupa.gif)

---

## ⚙️ Instalação e Execução

1. **Clone o repositório:**
   ```bash
   git clone [https://github.com/seu-usuario/color-lab-pro.git](https://github.com/seu-usuario/color-lab-pro.git)
