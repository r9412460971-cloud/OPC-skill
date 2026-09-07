# 前端模式参考（编辑级金融终端）

单文件 `index.html`（Tailwind CDN + 原生 JS，无图表库、无构建步骤），fetch 同目录 `data.json` 渲染。
本文件给出各组件的最小可用模式，可直接改写复用。

## 目录

- 设计系统 tokens
- 数字格式化（A 股红涨绿跌）
- SVG 折线图（带十字光标 tooltip）
- 卡片迷你火花线
- 弹窗深度视图
- 板块卡通形象（手绘 SVG + CSS 动画）
- 组合回测（按日再平衡 + 日期对齐）
- 风险回报散点图
- 口号横幅（渐变流光字）
- 本地验证循环

## 设计系统 tokens

```css
:root {
  --paper: #F5F4F0;  /* 暖纸底 */
  --ink: #1B1A17;    /* 主文字 */
  --ink-2: #6B675E;  /* 次文字 */
  --line: #E4E1D9;   /* 发丝线 */
  --card: #FDFCFA;   /* 卡片底 */
  --up: #D43A2F;     /* A股惯例：红涨 */
  --down: #14954F;   /* 绿跌 */
}
.num { font-variant-numeric: tabular-nums; }          /* 数字必须等宽 */
.display { font-family: "Songti SC", "Noto Serif SC", serif; } /* 标题衬线 */
.card { background: var(--card); border: 1px solid var(--line); border-radius: 14px; }
```

模块配色建议各给一个 accent（本项目：老登 `#7C5CBF`、中登 `#3E7CB1`、小登 `#D98E2B`），
用于 pill、火花线、散点、滑杆 `accent-color`。

## 数字格式化

```js
// Wind 涨跌幅字段本身已是百分数（-2.47 即 -2.47%），严禁再乘 100
const p = v => (v == null || isNaN(v)) ? '—' : (v > 0 ? '+' : '') + Number(v).toFixed(2) + '%';
const clsByVal = v => (v == null || isNaN(v)) ? 'neutral' : (v > 0 ? 'up' : v < 0 ? 'down' : 'neutral');
const capFmt = v => v >= 1e12 ? (v/1e12).toFixed(2)+' 万亿' : v >= 1e8 ? (v/1e8).toFixed(0)+' 亿' : '—';
```

## SVG 折线图（带十字光标 tooltip）

viewBox 880×300，手写网格线 + 渐变面积 + 主线；mousemove 时按 x 坐标取最近数据点，
移动竖线/圆点/tooltip。tooltip 用绝对定位 div（`transform: translate(-50%,-115%)`，
靠右 `>74%` 改 `-98%`、靠左 `<26%` 改 `-2%` 防溢出）。区间切换按钮 = 对 series 数组 slice 后重绘。
触屏用 `touchmove` 复用同一处理函数（`{passive:true}`）。

## 卡片迷你火花线

取 series 末 60 点，viewBox 220×46，`preserveAspectRatio="none"`，模块色 1.6px 线 + 透明渐变面积，末端圆点。
非交互。

## 弹窗深度视图

- 遮罩：`position:fixed; inset:0; background:rgba(27,26,23,.45); backdrop-filter:blur(6px)`，class 切换 opacity
- 弹窗：`max-width:960px; max-height:90vh; overflow-y:auto`，进入时 `translateY(24px) scale(.985) → none`
- 关闭：Esc / 点遮罩 / 关闭按钮；打开时 `body.style.overflow='hidden'`

## 板块卡通形象（手绘 SVG + CSS 动画）

设计要点：viewBox 120×140；圆形/圆角矩形为主，一种主色 + 一个点缀色；底部投影椭圆；
`overflow:visible` 让形象探出卡片上缘（容器负 margin-top）。动作用纯 CSS keyframes：

```css
.m-sway { transform-origin: 60px 128px; animation: mSway 4.6s ease-in-out infinite; }  /* 老登摇摆 */
.m-bob { animation: mBob 3.4s ease-in-out infinite; }                                  /* 中登漂浮 */
.m-blink { transform-box: fill-box; transform-origin: center; animation: mBlink 4.8s infinite; } /* 小登眨眼 */
@keyframes mBlink { 0%,90%,100% { transform: scaleY(1); } 94% { transform: scaleY(.1); } }
/* SVG 子元素动画必须 transform-box: fill-box；必须配 prefers-reduced-motion 降级 */
```

## 组合回测（按日再平衡 + 日期对齐）

```js
// 1. 日期对齐：并集排序 + 前值填充；起点 = 各序列首个非空日期的最大值
// 2. 权重归一：ws = weights / sum(weights)，允许用户输入和 ≠100 时仍先归一回测
// 3. 逐日：port[i] = port[i-1] * (1 + Σ ws[k] * (close[k][i]/close[k][i-1] - 1))
// 4. 指标：区间收益=port末/100-1；最大回撤=峰值回撤；胜率=日收益>0占比；波动率=std*sqrt(252)
// 5. 成分对比线：各序列 close/close[0]*100 归一化，与组合线同图
```

槽位交互：3 个固定槽，select 按模块 optgroup；选重时两槽交换（不是禁止）；滑杆 input 事件只更新数值+重算（不重建 DOM），select change 才重建。

## 风险回报散点图

X=近一年最大回撤（负值，左深右浅，xMax=0），Y=近一年回报。指数按模块色落点；
组合=黑色菱形（旋转正方形 path）+ 外圈环 + 加粗标签（`paint-order:stroke` 白色描边防压线）。
悬停：预存各点 SVG 坐标，mousemove 找 24 单位内最近点，显示高亮环 + tooltip。
组合指标用独立全窗口计算，不受主图区间按钮影响。

## 口号横幅（渐变流光字）

```css
.slogan-bar { background:#14130F; text-align:center; padding:11px; }
.slogan-text { font-weight:900; letter-spacing:.16em;
  background: linear-gradient(90deg,#9B7FD4,#5FA0CE,#EDB254,#9B7FD4); background-size:300% 100%;
  -webkit-background-clip:text; background-clip:text; color:transparent;
  animation: sloganFlow 7s linear infinite; filter: drop-shadow(0 0 14px rgba(124,92,191,.4)); }
@keyframes sloganFlow { to { background-position: 300% 0; } }
/* 尾部打字光标 ▍ 用 steps(1) 闪烁 */
```

## 本地验证循环（改完必跑）

```bash
# 1. JS 语法
python3 -c "import re;s=open('index.html').read();open('/tmp/x.js','w').write('\n'.join(re.findall(r'(?s)<script>(.*?)</script>',s)))" && node --check /tmp/x.js
# 2. 本地起服 + headless Chrome 截图自查（AI 必须自己看图确认）
python3 -m http.server 8123 &
"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --headless --disable-gpu \
  --window-size=1400,3000 --screenshot=/tmp/shot.png --virtual-time-budget=9000 --hide-scrollbars \
  "http://localhost:8123/index.html"
# 3. 看截图 → 改 → 再截。测弹窗/灯箱：注入自动点击脚本；测 tooltip：注入强制 display 的 CSS
# 注意：file:// 下 fetch data.json 会被 CORS 拦，必须 http://localhost
# 注意：headless 最小窗口宽度 ~485px，390px 截图右侧裁切是工具伪影，不是真溢出
```
