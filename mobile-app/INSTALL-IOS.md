# iOS 安装说明

这条 [`codex/app-shell`](/Users/Zhehua/Desktop/Mannheim/CODE-app-shell) 分支现在已经改成 iOS 方向。

它的目标是：

- 保留你现有的 Flask 网站和线上部署
- 把 `https://app.zhzhehua.com` 包成一个只给你自己安装的 iPhone App 壳
- 后面继续接相机、定位、分享等能力

## 先说最重要的一点

在你现在这台 Windows 电脑上，我已经把 iOS 壳代码和 `ios/` 工程骨架准备好了。  
但真正签名、安装到 iPhone，还是要在 **Mac + Xcode** 上完成。

## 你以后在 Mac 上要执行的命令

进入 [`CODE-app-shell`](/Users/Zhehua/Desktop/Mannheim/CODE-app-shell) 后：

```bash
npm install
npm run cap:sync:ios
npm run cap:open:ios
```

然后：

1. 用 Xcode 打开 iOS 工程
2. 选择你自己的 Apple ID / Team
3. 连接 iPhone
4. 直接运行安装

## 当前这一版已经做好的事情

- App 名称已经配置好：`Moments Library`
- App 会直接加载你线上已经可用的网站
- 这意味着你网站更新后，App 打开看到的内容也会跟着更新
- `ios/` 工程已经存在，不需要重新从零生成

## 下一步最值得做的增强

- 自定义 iOS 图标
- 启动页
- 相机能力
- 定位能力
- 更像原生 App 的分享入口
