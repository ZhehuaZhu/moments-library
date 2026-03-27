# Android 安装说明

这条 `codex/app-shell` 分支已经生成了一个最小的 Android App 壳。

当前版本的作用：

- 把线上站点 `https://app.zhzhehua.com` 包成一个你自己手机可安装的 Android 应用入口。
- 先解决“像 App 一样安装和打开”的问题。
- 相机、定位、分享这类更深的原生能力，放到下一阶段再接。

## 你以后主要会用到的命令

在 [`CODE-app-shell`](/Users/Zhehua/Desktop/Mannheim/CODE-app-shell) 目录里运行：

```bash
npm install
npm run cap:sync
npm run cap:open:android
```

## 最简单的使用方法

1. 进入 `CODE-app-shell`
2. 执行 `npm run cap:sync`
3. 执行 `npm run cap:open:android`
4. 用 Android Studio 打开后，连接手机，直接运行

## 当前版本的特点

- 会直接加载你已经上线的网站
- 所以网站一更新，App 打开后看到的也是新内容
- 这是最适合你现在项目阶段的第一版方案

## 下一步建议

后面如果你要更像真正原生 App，可以继续补：

- 相机上传
- 定位
- 系统分享
- 启动页和图标
- 更适合手机的导航和页面
