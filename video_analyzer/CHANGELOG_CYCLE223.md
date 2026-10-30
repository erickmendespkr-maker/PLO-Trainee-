# Ciclo 223 — seleção de quadros por timestamp para revisão de ROIs

## Entrega

- Novo `offline_roi_frame_review.py`: recebe vídeo MP4/WebM autorizado, plano de mãos previamente revisado, template de geometria das mesas e seleção explícita de até 12 timestamps por mão.
- Valida SHA-256 do vídeo contra o plano, limites dos timestamps dentro das mãos, resolução, duração, geometria de até quatro mesas e integridade dos arquivos de entrada.
- Extrai quadros com FFmpeg e cria uma página `index.html` sem rede com links para **um editor visual autônomo por quadro** (`offline_table_roi_editor.py`). Cada editor exporta um template JSON individual; alterações não são propagadas automaticamente entre quadros.
- `manifest.json` contém hashes SHA-256 dos quadros, editores, índice e entradas, mais flags explícitas de ausência de confirmação OCR, rastreamento e elegibilidade matemática.
- Proteções: seleção estrita, limite de 12 quadros e 64 MiB de imagens extraídas, rejeição de links simbólicos nas entradas, diretório de saída exclusivo, staging e limpeza após falhas.

## Uso

```bash
cd video_analyzer
python offline_roi_frame_review.py session.mp4 plan.json template.json frames.json review_frames
```

Formato de `frames.json`:

```json
{
  "schema_version": 1,
  "status": "human_selected_frame_timestamps_unverified",
  "frames": [
    {"hand_id": "H1", "pts_seconds": 10.5},
    {"hand_id": "H2", "pts_seconds": 34.25}
  ]
}
```

A pasta `review_frames` não pode existir antes da execução. Abra `review_frames/index.html`, revise cada quadro e salve os templates corrigidos. **Esses templates não são cartas/ações confirmadas.**

## Testes

- 17 testes novos de seleção, segurança, hashes, FFmpeg sintético, editor offline e falhas controladas.
- Suíte local selecionada: 139 testes passaram (não é a suíte integral do repositório).
- Os testes não usam vídeo real de pôquer nem comprovam precisão OCR, rastreamento de mesas, reconhecimento de ações ou desempenho de sessões de 40–60 minutos.

## Limitações e bloqueios

- As mãos, timestamps e regiões das mesas são declarados/revisados por humanos.
- O índice permite navegar entre editores, mas não mantém alterações sincronizadas entre quadros.
- O fluxo não confirma OCR, não reconstrói mãos automaticamente, não calcula equity/EV e não exporta cortes novos.
- Falta um vídeo real autorizado e anotado de 3–5 minutos para medir precisão e calibrar o reconhecimento.
- Não testado no Windows. Não foram utilizados GitHub Actions, produção, credenciais ou serviços pagos.
