# 个人朋友圈 + 知识/媒体库

一个基于 Flask 的全栈 Web 应用，支持公开浏览、管理员登录、多附件动态发布、分类管理、中文地址解析、软删除和回收站。

## 技术栈

- Flask + Jinja2
- Flask-SQLAlchemy + Flask-Migrate
- Flask-Login + Flask-WTF
- SQLite
- 原生 HTML / CSS / JavaScript

## 本地启动

当前仓库已经包含完整代码，但本机环境里尚未检测到可用的 Python。请先安装 Python 3.11 或更高版本，然后执行：

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## 初始化数据库与管理员

```powershell
$env:FLASK_APP="run.py"
flask init-db
flask init-admin
```

这会在 `instance/app.db` 中创建 SQLite 数据库，并初始化单个管理员账号。

如果你想接入 Flask-Migrate 的迁移工作流，也可以在安装环境后执行：

```powershell
flask db init
flask db migrate -m "init schema"
flask db upgrade
```

## 运行应用

```powershell
flask run --debug
```

默认访问地址为 [http://localhost:5000](http://localhost:5000)。

## 主要能力

- 公开信息流浏览
- 管理员登录、发布动态、创建分类
- 图片、视频、PDF、文档多附件混合上传
- UUID 重命名上传文件，防止中文名和空格导致的存储问题
- 浏览器定位 + Nominatim 中文逆地址解析
- 左侧分类筛选与卡片内即时改分类
- 软删除、回收站恢复和 30 天清理命令

## 测试

```powershell
pytest
```

测试覆盖了登录、公开/管理员权限、发布上传、分类修改、软删除恢复和逆地址解析接口。
