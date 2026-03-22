PASSO A PASSO DO ZERO

1) Instale o Python 3.11 ou mais novo.
   Na instalação, marque a opção "Add Python to PATH".

2) Extraia a pasta quiz_app em qualquer lugar do PC.

3) Abra a pasta e clique na barra de endereço.
   Digite cmd e aperte Enter.

4) Instale as dependências:
   pip install -r requirements.txt

5) Rode o projeto:
   python app.py

6) Abra no navegador:
   http://127.0.0.1:5000

COMO USAR

- Participante:
  Digita o nome com pelo menos 3 caracteres e um elemento: 🔥 🌪️ ⚡ 💧 🌑
  Exemplo: Maria ⚡

- DEV:
  No canto superior direito, digite a senha 0832.
  Entrando no painel, você pode:
  - Iniciar quiz
  - Fechar quiz
  - Limpar resultados

REGRAS IMPORTANTES

- O quiz sorteia 25 perguntas aleatórias.
- O tempo total é 1 minuto e 30 segundos.
- Cada participante só joga 1 vez por rodada.
- O bloqueio usa o token salvo na sessão do navegador e também trava nome repetido na rodada.
- Ao clicar em Limpar, os resultados são apagados, uma nova rodada é criada e o quiz fecha.

ONDE EDITAR

No arquivo app.py:
- DEV_PASSWORD = "0832"
- TOTAL_QUESTIONS = 25
- TOTAL_TIME_SECONDS = 90

No arquivo perguntas.json:
- Edite, remova ou adicione perguntas.
- Sempre deixe pelo menos 25 perguntas.
