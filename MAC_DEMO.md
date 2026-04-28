# macOS Demo

这是一套不依赖 Windows 的 macOS 本机演示入口。它复用同一套 FastAPI + SQLite + MockOCR 后端，并提供一个极简浏览器演示页，方便先给别人展示完整流程。

## 一键验证

```bash
cd /Users/yumei/machine-label-ocr
./scripts/smoke_mac_demo.sh
```

## 一键启动

```bash
cd /Users/yumei/machine-label-ocr
./scripts/run_mac_demo.sh
```

也可以在 Finder 里双击项目根目录的：

```text
Start Mac Demo.command
```

启动后打开：

```text
http://127.0.0.1:8000
```

API 文档：

```text
http://127.0.0.1:8000/docs
```

如果 `8000` 端口已被占用，脚本会直接打开已有页面。若想另开端口：

```bash
PORT=8010 ./scripts/run_mac_demo.sh
```

然后打开：

```text
http://127.0.0.1:8010
```

如果要让同一 WiFi 下的手机访问，把 `127.0.0.1` 换成这台 Mac 的局域网 IP。

默认启动只监听本机。需要局域网展示时使用：

```bash
HOST=0.0.0.0 ./scripts/run_mac_demo.sh
```

这会把演示服务暴露给同一局域网设备，只建议在可信网络中使用。

## 演示流程

1. 打开 `http://127.0.0.1:8000`。
2. 选择品类 `A/B/C`。
3. 上传一张 `.jpg/.jpeg/.png/.webp` 图片。
4. 页面会调用 MockOCR，显示解析出的 Model / VIN/BIN / SN。
5. 可人工修改字段。
6. 点击确认入库。
7. 页面可查看待确认记录和已确认记录。
8. 点击导出 CSV 下载已确认记录。

## 当前演示边界

- 默认使用 MockOCR；可按下方配置启用真实 Tesseract OCR 与条码识别。
- 不接 SaaS，不写 Playwright。
- 图片只保存在本机 `data/uploads/`。
- 数据库是本机 SQLite：`data/app.db`。

## 启用真实 OCR 与条码识别

```bash
brew install zbar tesseract
.venv/bin/pip install -e ".[barcode,ocr]"
```

在 `config/settings.yaml` 中设置：

```yaml
app:
  ocr_provider: tesseract
  enable_barcode: true
```

重启演示服务：

```bash
./scripts/run_mac_demo.sh
```
