# Vasi 统一登录

本 Chart 独立安装；`auth.mode: external` 保留已有部署方接线，`auth.mode: oidc` 消费 Vasi 登记的身份源。
`publicUrl` 必须是包含入口端口的 HTTPS origin，`ingress.host` 必须匹配它。客户端、回调、角色和命名空间由 Vasi 的受管 SSO 操作登记；仅上传 Chart 不会创建身份客户端或授予用户权限。

Vasi 写入专属 CA ConfigMap 和凭据 Secret 的引用；values 只保存引用，不保存密码、客户端密钥或用户令牌。制品发布者必须把所有主容器、初始化容器和 sidecar 镜像纳入完整材料清单并提供已导入 Nexus 的固定摘要。

需要 `auth.oidc.existingSecret`（`issuer/client-id/client-secret`）、`auth.oidc.directorySecret`（相同键，只读目录服务账号）、`adminSecret`（`username/password`，用户名为 `automation`）。`provisioner.image` 使用本仓库 `deploy/sso/Dockerfile` 构建；`provisioner.existingSecret` 提供 `users.json` 与 `shared-bucket`。

`users.json` 是 `[{"subject":"IAM subject","bucket":"files-personal-member","credential":{"accessKey":"…","secretKey":"…"}}]`。这些是存储凭据，只能放 Secret。存储运营方事先建好桶，并把每个 key 限定到此人的个人桶及团队桶；`provisioner.s3Endpoint/s3Region` 指向该存储。授予 `files-user` 不会自动创建桶或扩大存储权限。

产品 sidecar 仅通过 Pod loopback 管理 API 创建属于当前 issuer 的账号及两个挂载；目录只读，不能授予 IAM 角色。没有完整目录快照就不发布新投影；撤销资格会停用已管理账号。首次绑定后的 issuer/client ID 不得改绑。已有未标记账号或同名文件夹会拒绝接管，需维护人员核对，不能按同名认领。

WebClient 暴露 8080；管理 API 8081 仅监听 loopback，不经 Service/Ingress 暴露。原有 Files/S3 初始化流程仍可在 external 模式使用。迁移存量身份或换 issuer 不属于自动安装流程。

投影每十秒刷新，完整目录扫描有两分钟期限；readiness 检查最近一次成功的时间，超过两分钟关闭入口，不能用永远存在的 ready 文件掩盖卡住的同步进程。
