# EPG 合并

把多个国家的 XMLTV 节目单合并成一个文件,每天自动更新,给 TiviMate 用。

合并在 GitHub 的服务器上完成,不占用自己的设备。

## 部署步骤

**1. 建仓库**

在 GitHub 新建一个仓库,名字随意(下面假设叫 `epg`),**必须选 Public** —— 免费账号的 GitHub Pages 不支持私有仓库。

把这三个文件放进去:

```
merge_epg.py
sources.txt
.github/workflows/merge-epg.yml
```

目录结构要对,`merge-epg.yml` 必须在 `.github/workflows/` 里面,Actions 才认。

**2. 打开 Pages**

仓库 → Settings → Pages → Build and deployment 下面的 Source,选 **GitHub Actions**(不是 Deploy from a branch)。

**3. 跑第一次**

仓库 → Actions 标签页 → 左边选「合并 EPG」→ 右边 **Run workflow** 按钮 → 确认。

等两三分钟,绿勾出现就是成功了。点进去能看到每个源抓了多少频道、多少节目。

**4. 拿链接**

```
https://你的用户名.github.io/epg/guide.xml.gz
```

把这条填进 TiviMate 的 EPG 设置。`guide.xml`(不带 .gz)也能用,但体积大好几倍,建议用 gz。

## 日常维护

加减国家就改 `sources.txt`,在网页上直接编辑、提交即可 —— 工作流配了 `push` 触发,改完会立刻重跑一次,不用等到第二天。

加新链接前先用浏览器打开确认不是 404,`epgshare01` 的国家编号偶尔会变(CA1 变 CA2 这种)。

## 关于这个工作流

`.github/workflows/merge-epg.yml` 里几个关键部分:

**`on:`** 决定什么时候跑。这里配了三种触发方式:定时(`schedule`)、手动点按钮(`workflow_dispatch`)、改了 sources.txt 就跑(`push` + `paths`)。

**`cron: '0 20 * * *'`** 五个字段是「分 时 日 月 星期」,用的是 **UTC 时间**。UTC 20:00 等于北京时间次日 04:00。想改时间就调前两个数字,注意换算时区。

另外 GitHub 的定时任务不保证准点,整点前后经常排队延迟几十分钟,属正常现象。

**`jobs:`** 下面是具体干的活。`merge` 这个 job 里的 `steps` 按顺序执行:拉代码 → 装 Python → 跑脚本 → 打包产物。`deploy` 这个 job 用 `needs: merge` 声明了依赖,前一个成功了才会开始。

**`uses:`** 是引用别人写好的现成动作(action),比如 `actions/checkout@v4` 就是官方的「把仓库代码拉到运行环境里」。`@v4` 是版本号,锁版本比用 `@main` 稳。

**`run:`** 是直接执行 shell 命令。

**`permissions:`** 声明这个工作流需要什么权限。发布 Pages 需要 `pages: write`,不写会报权限错误。

## 脚本做了什么

`merge_epg.py` 针对多源合并容易出的问题做了处理:

- 每个源独立超时(90 秒)加两次重试,**某个源挂掉只跳过它**,不影响其他源 —— 这是 Threadfin 之类工具最容易出问题的地方,一个坏源能堵死整个队列
- 靠文件头判断是不是 gzip,不管后缀写的什么
- 同一个频道 ID 在多个源里重复出现时,只保留 `sources.txt` 里**靠前**那个源的数据,连带它的节目一起,避免节目单出现重复条目
- 流式解析,内存占用跟文件大小无关

只有当所有源全部失败时,任务才会报红。
