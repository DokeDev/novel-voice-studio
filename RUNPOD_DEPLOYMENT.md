# RunPod 部署与运行

这个项目应部署为 **RunPod GPU Pod**，不建议第一版使用 Serverless。它包含管理界面、长时间音频生成、LoRA 训练和需要持续保存的项目状态，更适合常驻 Pod。

## 1. 构建并推送镜像

项目的 Docker 镜像只包含程序和依赖，不包含 Qwen3-TTS 模型。以下以 Docker Hub 为例：

```bash
docker login
docker buildx build \
  --platform linux/amd64 \
  -t YOUR_DOCKERHUB_USER/alexandria-tts:latest \
  --push .
```

将 `YOUR_DOCKERHUB_USER` 替换成自己的用户名。使用 GHCR 或其他仓库也可以。私有镜像需要在 RunPod 中添加 Registry Credentials，并在 Pod 模板中选择对应凭据。

在 Apple Silicon Mac 上必须保留 `--platform linux/amd64`，RunPod 的 NVIDIA GPU 主机使用 x86_64 Linux。

## 2. 创建持久化存储

在 RunPod 控制台进入 **Storage / Network Volumes**：

1. 创建至少 `100 GB` 的 Network Volume。
2. 记住它所在的数据中心。
3. 创建 Pod 时选择相同数据中心并挂载该 Volume。
4. 挂载路径使用 `/workspace`。

模型、上传小说、声音参考、LoRA、脚本和最终音频都会保存到：

```text
/workspace/alexandria/
```

Pod 被删除后，只要 Network Volume 仍在，这些数据就可以挂载到新的 Pod。

## 3. 创建 GPU Pod

建议的首台机器：

| 项目 | 建议值 |
|---|---|
| GPU | RTX 4090 24GB、L4 24GB 或其他 24GB NVIDIA GPU |
| GPU 数量 | 1 |
| Container Disk | 30 GB |
| Network Volume | 100 GB 起 |
| Volume Mount Path | `/workspace` |
| HTTP Port | `4200` |

生成测试可以使用 16GB 显存；要训练 LoRA，24GB 更稳妥。

在 Pod 的自定义模板中设置：

- **Container Image**：`YOUR_DOCKERHUB_USER/alexandria-tts:latest`
- **Container Start Command / Docker Args**：留空，使用镜像自带的启动命令
- **Expose HTTP Ports**：`4200`
- **TCP Ports**：无需为 Web UI 额外开放

添加以下环境变量：

```text
ALEXANDRIA_HOST=0.0.0.0
ALEXANDRIA_PORT=4200
ALEXANDRIA_DATA_DIR=/workspace/alexandria
ALEXANDRIA_CONFIG_PATH=/workspace/alexandria/config/config.json
ALEXANDRIA_MODELS_DIR=/workspace/alexandria/models
ALEXANDRIA_OUTPUT_DIR=/workspace/alexandria/final
ALEXANDRIA_ENABLE_BUILTIN_LORA=false
HF_HOME=/workspace/alexandria/cache/huggingface
TZ=Asia/Shanghai
```

可选变量：

```text
HF_TOKEN=你的 Hugging Face Token
ALEXANDRIA_S3_ENDPOINT=你的 S3 兼容端点
ALEXANDRIA_S3_REGION=区域
ALEXANDRIA_S3_BUCKET=存储桶
ALEXANDRIA_S3_ACCESS_KEY_ID=访问密钥 ID
ALEXANDRIA_S3_SECRET_ACCESS_KEY=访问密钥
ALEXANDRIA_S3_PUBLIC_BASE_URL=CDN 或公开访问地址
ALEXANDRIA_S3_PREFIX=audiobooks
```

不要把 Token、LLM Key 或对象存储密钥写进镜像或 Git 仓库。

## 4. 启动和访问

### 新建或重建 Pod

只要 `/workspace` 仍然保留，进入项目目录后执行：

```bash
cd /workspace/novel-voice-studio
chmod +x bootstrap.sh start.sh
./bootstrap.sh
```

`bootstrap.sh` 会检查并按需恢复系统音频工具、Python 虚拟环境和项目依赖，然后调用 `start.sh` 启动服务。已有且版本匹配的环境会直接复用；模型、小说、音色和生成结果不会被重新下载或删除。

可选命令：

```bash
./bootstrap.sh --check       # 只检查，不安装、不启动
./bootstrap.sh --no-start    # 安装环境，但不启动
./bootstrap.sh --force       # 强制重建 Python 虚拟环境
```

建议继续使用带有 PyTorch、CUDA 和 cuDNN 的 RunPod GPU 镜像。脚本会复用镜像自带的 PyTorch；如果基础镜像没有 Python/PyTorch，应更换镜像，而不是在每次启动时重新下载整套 CUDA 运行时。

### 日常重启

环境已经安装后可直接使用启动脚本：

```bash
cd /workspace/novel-voice-studio
./start.sh
```

脚本会自动检查 `4200` 端口和旧的 `app.pid`，停止旧进程后重新启动服务。只有健康检查成功后才会写入新 PID；启动失败时会直接显示最近的日志。

以后更新和重启只需要：

```bash
cd /workspace/novel-voice-studio
git pull origin main
./start.sh
```

正常情况下会显示 Uvicorn 已监听 `0.0.0.0:4200`。

RunPod HTTP Proxy 地址格式为：

```text
https://POD_ID-4200.proxy.runpod.net
```

也可以在 Pod 的 **Connect** 页面点击 `HTTP Service [Port 4200]`。

进入 Pod 终端后可以检查：

```bash
nvidia-smi
python -c 'import requests; print(requests.get("http://127.0.0.1:4200/api/models").json())'
```

## 5. 安装模型

第一次进入管理界面后打开 **模型**：

1. 先安装 `Qwen3-TTS 1.7B CustomVoice`，用于 9 个官方预置音色。
2. 需要声音克隆或 LoRA 时，再安装 `Qwen3-TTS 1.7B Base`。
3. 需要文字设计音色时，再安装 `Qwen3-TTS 1.7B VoiceDesign`。

管理员可以在模型页面手动点击下载；下载内容会进入持久盘：

```text
/workspace/alexandria/models/qwen3-tts/1.7b-custom-voice
/workspace/alexandria/models/qwen3-tts/1.7b-base
/workspace/alexandria/models/qwen3-tts/1.7b-voice-design
```

不需要一次下载三个模型。只测试预置音色时，先下载 CustomVoice 即可。

## 6. 首次配置和测试

在 **设置** 页面填写：

- LLM Base URL：一个可从 RunPod 访问的 OpenAI 兼容接口
- LLM API Key：对应接口密钥
- LLM Model Name：接口中的模型名称
- TTS 模式：`local`
- TTS 设备：`cuda:0` 或 `auto`
- 语言：`Chinese`

保存后执行最短验证流程：

1. 上传一小段 TXT。
2. 生成标注脚本。
3. 在“声音”中给角色选择 `Serena`、`Vivian`、`Dylan` 等预置音色。
4. 在“编辑”中只生成一两条语音。
5. 确认声音正常后再批量生成整本小说。

## 7. 停机和重新部署

- **Stop Pod**：停止 GPU 计费，但 Network Volume 仍会产生存储费用。
- **Terminate Pod**：删除当前 Pod。重新创建时挂载同一个 Network Volume 即可恢复数据。
- 不要把重要模型和项目只放在 Container Disk；Container Disk 不应视为长期备份。

当前管理界面没有登录认证。测试阶段不要把代理地址公开传播；正式使用时应放在带认证的反向代理或 VPN 后面，订单平台也不应直接访问这个管理界面。
