import React from "react";
import {
  AbsoluteFill,
  interpolate,
  Sequence,
  useCurrentFrame,
  useVideoConfig,
  spring,
  Audio,
  staticFile,
  Series,
} from "remotion";

// ─── Design Tokens ────────────────────────────────────────────────
const COLORS = {
  bg: "#0b0f19",
  cardBg: "#111827",
  accent: "#3b82f6",
  accentGlow: "#60a5fa",
  green: "#10b981",
  yellow: "#f59e0b",
  red: "#ef4444",
  purple: "#8b5cf6",
  white: "#f8fafc",
  muted: "#94a3b8",
  border: "#1e293b",
};

const FONT = {
  title: '"SF Pro Display", "Helvetica Neue", sans-serif',
  body: '"SF Pro Text", "Helvetica Neue", sans-serif',
  mono: '"JetBrains Mono", "Fira Code", monospace',
};

// ─── Shared Components ──────────────────────────────────────────────

const TitleSlide: React.FC<{
  title: string;
  subtitle?: string;
  accentColor?: string;
}> = ({ title, subtitle, accentColor = COLORS.accent }) => {
  const frame = useCurrentFrame();
  const fadeIn = interpolate(frame, [0, 20], [0, 1], { extrapolateRight: "clamp" });
  const slideUp = spring({ frame, fps: 30, config: { damping: 15 } });

  return (
    <AbsoluteFill
      style={{
        background: `linear-gradient(135deg, ${COLORS.bg} 0%, #0f172a 100%)`,
        justifyContent: "center",
        alignItems: "center",
        padding: 80,
      }}
    >
      <div
        style={{
          transform: `translateY(${(1 - slideUp) * 40}px)`,
          opacity: fadeIn,
        }}
      >
        <h1
          style={{
            fontSize: 72,
            fontWeight: 700,
            color: COLORS.white,
            fontFamily: FONT.title,
            textAlign: "center",
            marginBottom: 24,
            lineHeight: 1.2,
          }}
        >
          {title.split(" ").map((word, i) => (
            <span key={i}>
              {i > 0 && " "}
              <span style={{ color: i % 3 === 0 ? accentColor : undefined }}>
                {word}
              </span>
            </span>
          ))}
        </h1>
        {subtitle && (
          <p
            style={{
              fontSize: 28,
              color: COLORS.muted,
              fontFamily: FONT.body,
              textAlign: "center",
              maxWidth: 800,
              margin: "0 auto",
            }}
          >
            {subtitle}
          </p>
        )}
      </div>
    </AbsoluteFill>
  );
};

const SectionHeader: React.FC<{ title: string; index: string }> = ({
  title,
  index,
}) => {
  const frame = useCurrentFrame();
  const fadeIn = interpolate(frame, [0, 15], [0, 1], { extrapolateRight: "clamp" });

  return (
    <div
      style={{
        opacity: fadeIn,
        marginBottom: 48,
      }}
    >
      <div
        style={{
          fontSize: 18,
          color: COLORS.accent,
          fontFamily: FONT.mono,
          letterSpacing: 3,
          marginBottom: 8,
        }}
      >
        {index}
      </div>
      <h2
        style={{
          fontSize: 48,
          fontWeight: 700,
          color: COLORS.white,
          fontFamily: FONT.title,
          margin: 0,
        }}
      >
        {title}
      </h2>
    </div>
  );
};

const Card: React.FC<{
  children: React.ReactNode;
  style?: React.CSSProperties;
}> = ({ children, style }) => (
  <div
    style={{
      background: COLORS.cardBg,
      border: `1px solid ${COLORS.border}`,
      borderRadius: 12,
      padding: 32,
      ...style,
    }}
  >
    {children}
  </div>
);

const CodeBlock: React.FC<{ code: string; language?: string }> = ({
  code,
  language = "bash",
}) => {
  const frame = useCurrentFrame();
  const fadeIn = interpolate(frame, [0, 10], [0, 1], { extrapolateRight: "clamp" });

  return (
    <div
      style={{
        opacity: fadeIn,
        background: "#0a0e17",
        border: `1px solid ${COLORS.border}`,
        borderRadius: 8,
        padding: "20px 28px",
        fontFamily: FONT.mono,
        fontSize: 22,
        color: COLORS.green,
        whiteSpace: "pre-wrap",
        lineHeight: 1.6,
      }}
    >
      {code}
    </div>
  );
};

const BulletList: React.FC<{ items: string[] }> = ({ items }) => {
  const frame = useCurrentFrame();
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      {items.map((item, i) => {
        const delay = i * 8;
        const itemFadeIn = interpolate(frame, [delay, delay + 15], [0, 1], {
          extrapolateRight: "clamp",
        });
        return (
          <div
            key={i}
            style={{
              opacity: itemFadeIn,
              display: "flex",
              alignItems: "flex-start",
              gap: 12,
            }}
          >
            <span
              style={{
                color: COLORS.accent,
                fontSize: 24,
                marginTop: 2,
              }}
            >
              ◆
            </span>
            <span
              style={{
                color: COLORS.white,
                fontFamily: FONT.body,
                fontSize: 24,
              }}
            >
              {item}
            </span>
          </div>
        );
      })}
    </div>
  );
};

const FlowStep: React.FC<{
  step: number;
  title: string;
  desc: string;
  delay?: number;
}> = ({ step, title, desc, delay = 0 }) => {
  const frame = useCurrentFrame();
  const fadeIn = interpolate(frame, [delay, delay + 15], [0, 1], {
    extrapolateRight: "clamp",
  });

  return (
    <div
      style={{
        opacity: fadeIn,
        display: "flex",
        alignItems: "center",
        gap: 20,
        marginBottom: 24,
      }}
    >
      <div
        style={{
          width: 48,
          height: 48,
          borderRadius: "50%",
          background: COLORS.accent,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          color: COLORS.white,
          fontFamily: FONT.title,
          fontSize: 20,
          fontWeight: 700,
          flexShrink: 0,
        }}
      >
        {step}
      </div>
      <div>
        <div style={{ color: COLORS.white, fontSize: 22, fontWeight: 600 }}>
          {title}
        </div>
        <div style={{ color: COLORS.muted, fontSize: 16 }}>{desc}</div>
      </div>
      {step < 6 && (
        <div
          style={{
            marginLeft: "auto",
            color: COLORS.muted,
            fontSize: 20,
          }}
        >
          ↓
        </div>
      )}
    </div>
  );
};

// ─── Slide Content Components ────────────────────────────────────────

// Screenshot simulation component
const MockWindow: React.FC<{
  titleBar?: string;
  children: React.ReactNode;
}> = ({ titleBar = "AIOS Launcher", children }) => (
  <div
    style={{
      background:COLORS.cardBg,
      border: `1px solid ${COLORS.border}`,
      borderRadius: 12,
      overflow: "hidden",
      width: "100%",
      maxWidth: 960,
      boxShadow: "0 25px 50px -12px rgba(0,0,0,0.5)",
    }}
  >
    <div
      style={{
        background: "#0a0e17",
        padding: "12px 20px",
        display: "flex",
        alignItems: "center",
        gap: 8,
        borderBottom: `1px solid ${COLORS.border}`,
      }}
    >
      <div
        style={{ width: 12, height: 12, borderRadius: "50%", background: COLORS.red }}
      />
      <div
        style={{ width: 12, height: 12, borderRadius: "50%", background: COLORS.yellow }}
      />
      <div
        style={{ width: 12, height: 12, borderRadius: "50%", background: COLORS.green }}
      />
      <span
        style={{
          marginLeft: 12,
          color: COLORS.muted,
          fontSize: 13,
          fontFamily: FONT.body,
        }}
      >
        {titleBar}
      </span>
    </div>
    <div style={{ padding: 24 }}>{children}</div>
  </div>
);

const ProjectCard: React.FC<{
  name: string;
  path: string;
  status: "running" | "stopped";
  tasks: number;
}> = ({ name, path, status, tasks }) => (
  <div
    style={{
      background: "#1a2236",
      borderRadius: 10,
      padding: 20,
      border: `1px solid ${status === "running" ? COLORS.green : COLORS.border}`,
      minWidth: 280,
    }}
  >
    <div
      style={{
        display: "flex",
        justifyContent: "space-between",
        alignItems: "center",
        marginBottom: 12,
      }}
    >
      <span style={{ color: COLORS.white, fontWeight: 600, fontSize: 16 }}>
        {name}
      </span>
      <span
        style={{
          padding: "4px 10px",
          borderRadius: 20,
          fontSize: 12,
          fontWeight: 600,
          background: status === "running" ? "rgba(16,185,129,0.15)" : "rgba(148,163,184,0.15)",
          color: status === "running" ? COLORS.green : COLORS.muted,
        }}
      >
        {status === "running" ? "运行中" : "已停止"}
      </span>
    </div>
    <div style={{ color: COLORS.muted, fontSize: 12, marginBottom: 8 }}>
      {path}
    </div>
    <div style={{ color: COLORS.muted, fontSize: 12 }}>{tasks} 个任务</div>
  </div>
);

const FeatureGrid: React.FC<{
  features: { icon: string; title: string; desc: string }[];
}> = ({ features }) => {
  const frame = useCurrentFrame();
  return (
    <div
      style={{
        display: "grid",
        gridTemplateColumns: "repeat(2, 1fr)",
        gap: 20,
      }}
    >
      {features.map((f, i) => {
        const delay = i * 10;
        const itemFadeIn = interpolate(frame, [delay, delay + 15], [0, 1], {
          extrapolateRight: "clamp",
        });
        return (
          <Card key={i} style={{ opacity: itemFadeIn }}>
            <div style={{ fontSize: 32, marginBottom: 12 }}>{f.icon}</div>
            <div
              style={{ color: COLORS.white, fontSize: 22, fontWeight: 600, marginBottom: 8 }}
            >
              {f.title}
            </div>
            <div style={{ color: COLORS.muted, fontSize: 14 }}>{f.desc}</div>
          </Card>
        );
      })}
    </div>
  );
};

// ─── CLI Command Showcase ────────────────────────────────────────────

const CLICommand: React.FC<{
  cmd: string;
  desc: string;
  delay?: number;
}> = ({ cmd, desc, delay = 0 }) => {
  const frame = useCurrentFrame();
  const fadeIn = interpolate(frame, [delay, delay + 10], [0, 1], {
    extrapolateRight: "clamp",
  });

  return (
    <div style={{ opacity: fadeIn, marginBottom: 20 }}>
      <div
        style={{
          fontFamily: FONT.mono,
          fontSize: 20,
          color: COLORS.green,
          marginBottom: 4,
        }}
      >
        $ {cmd}
      </div>
      <div style={{ fontSize: 14, color: COLORS.muted }}>{desc}</div>
    </div>
  );
};

// ─── Main Tutorial Video ─────────────────────────────────────────────

export const AIOSTutorial: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const introDuration = 5 * fps; // 0-5
  const overviewDuration = 8 * fps; // 5-13
  const installDuration = 8 * fps; // 13-21
  const initScanDuration = 8 * fps; // 21-29
  const taskDuration = 10 * fps; // 29-39
  const routePackDuration = 10 * fps; // 39-49
  const executeDuration = 10 * fps; // 49-59
  const launcherDuration = 10 * fps; // 59-69
  const featuresDuration = 10 * fps; // 69-79
  const flowDuration = 10 * fps; // 79-89
  const cliDuration = 12 * fps; // 89-101
  const valueDuration = 8 * fps; // 101-109
  const outroDuration = 6 * fps; // 109-115

  const totalDuration =
    introDuration +
    overviewDuration +
    installDuration +
    initScanDuration +
    taskDuration +
    routePackDuration +
    executeDuration +
    launcherDuration +
    featuresDuration +
    flowDuration +
    cliDuration +
    valueDuration +
    outroDuration;

  let offset = 0;
  const nextOffset = (dur: number) => {
    const start = offset;
    offset += dur;
    return [start, start + dur - 1] as const;
  };

  const [
    introRange,
    overviewRange,
    installRange,
    initScanRange,
    taskRange,
    routePackRange,
    executeRange,
    launcherRange,
    featuresRange,
    flowRange,
    cliRange,
    valueRange,
    outroRange,
  ] = [
    nextOffset(introDuration),
    nextOffset(overviewDuration),
    nextOffset(installDuration),
    nextOffset(initScanDuration),
    nextOffset(taskDuration),
    nextOffset(routePackDuration),
    nextOffset(executeDuration),
    nextOffset(launcherDuration),
    nextOffset(featuresDuration),
    nextOffset(flowDuration),
    nextOffset(cliDuration),
    nextOffset(valueDuration),
    nextOffset(outroDuration),
  ];

  return (
    <AbsoluteFill style={{ background: COLORS.bg }}>
      {/* ─── 1. 开场 ─── */}
      <Sequence from={introRange[0]} durationInFrames={introRange[1] - introRange[0] + 1}>
        <TitleSlide
          title="AIOS 多模型开发中枢"
          subtitle="智能任务管理 · 模型路由 · 半自动执行 · 多项目工作台"
          accentColor={COLORS.accentGlow}
        />
      </Sequence>

      {/* ─── 2. 概述 ─── */}
      <Sequence from={overviewRange[0]} durationInFrames={overviewRange[1] - overviewRange[0] + 1}>
        <AbsoluteFill
          style={{
            background: COLORS.bg,
            padding: "80px 100px",
            justifyContent: "center",
          }}
        >
          <SectionHeader title="AIOS 是什么？" index="概述" />
          <BulletList
            items={[
              "本地文件系统型 AI 开发中枢",
              "为软件项目生成 .aios/ 知识目录",
              "扫描项目结构，管理开发任务",
              "智能推荐最合适的 AI 模型",
              "生成 Context Pack，一键复制给 AI 模型",
              "支持多项目管理与半自动执行",
            ]}
          />
        </AbsoluteFill>
      </Sequence>

      {/* ─── 3. 安装 ─── */}
      <Sequence from={installRange[0]} durationInFrames={installRange[1] - installRange[0] + 1}>
        <AbsoluteFill
          style={{
            background: COLORS.bg,
            padding: "80px 100px",
            justifyContent: "center",
          }}
        >
          <SectionHeader title="安装与启动" index="01" />
          <CodeBlock
            code={`# 克隆项目\ngit clone https://github.com/YX-NAS/AIOS.git\ncd AIOS\n\n# 创建虚拟环境并安装\npython3 -m venv .venv\nsource .venv/bin/activate\npip install -e ".[dev]"\n\n# 启动多项目首页\naios launcher --port 8755`}
          />
        </AbsoluteFill>
      </Sequence>

      {/* ─── 4. 初始化与扫描 ─── */}
      <Sequence from={initScanRange[0]} durationInFrames={initScanRange[1] - initScanRange[0] + 1}>
        <AbsoluteFill
          style={{
            background: COLORS.bg,
            padding: "80px 100px",
            justifyContent: "center",
          }}
        >
          <SectionHeader title="初始化与项目扫描" index="02" />
          <div style={{ display: "flex", gap: 32, alignItems: "flex-start" }}>
            <div style={{ flex: 1 }}>
              <CodeBlock
                code={`# 初始化 .aios/ 知识目录\naios init --root /path/to/project\n\n# 扫描项目文件\naios scan --root /path/to/project\n\n# 查看项目状态\naios status --root /path/to/project`}
              />
            </div>
            <div style={{ flex: 1 }}>
              <Card>
                <BulletList
                  items={[
                    "自动识别项目结构",
                    "生成文件索引",
                    "创建任务管理目录",
                    "识别技术栈构成",
                  ]}
                />
              </Card>
            </div>
          </div>
        </AbsoluteFill>
      </Sequence>

      {/* ─── 5. 任务管理 ─── */}
      <Sequence from={taskRange[0]} durationInFrames={taskRange[1] - taskRange[0] + 1}>
        <AbsoluteFill
          style={{
            background: COLORS.bg,
            padding: "80px 100px",
            justifyContent: "center",
          }}
        >
          <SectionHeader title="任务管理与拆解" index="03" />
          <div style={{ display: "flex", gap: 32, alignItems: "flex-start" }}>
            <div style={{ flex: 1 }}>
              <CodeBlock
                code={`# 创建任务\naios task create "修复登录超时"\n    --root ./myproject\n\n# 目标拆解\naios task plan "添加用户画像模块"\n    --root ./myproject\n\n# 查看任务列表\naios task list --root ./myproject`}
              />
            </div>
            <div style={{ flex: 1 }}>
              <Card>
                <BulletList
                  items={[
                    "按目标自动拆解子任务",
                    "识别技术栈构成",
                    "支持 bug / 功能开发两种拆解模式",
                    "拆分草案确认后再创建",
                  ]}
                />
              </Card>
            </div>
          </div>
        </AbsoluteFill>
      </Sequence>

      {/* ─── 6. 路由与 Pack ─── */}
      <Sequence from={routePackRange[0]} durationInFrames={routePackRange[1] - routePackRange[0] + 1}>
        <AbsoluteFill
          style={{
            background: COLORS.bg,
            padding: "80px 100px",
            justifyContent: "center",
          }}
        >
          <SectionHeader title="模型路由与 Context Pack" index="04" />
          <FlowStep step={1} title="智能路由" desc="任务类型匹配最合适的模型" delay={10} />
          <FlowStep step={2} title="Context Pack 生成" desc="整合项目背景、规则、相关文件" delay={25} />
          <FlowStep step={3} title="复制给 AI 模型" desc="一键复制或导出给 Codex / Claude Code" delay={40} />
          <div style={{ marginTop: 20, fontSize: 16, color: COLORS.muted, textAlign: "center" }}>
            系统会根据任务复杂度、类型、技术栈，从全局模型库推荐最佳模型
          </div>
        </AbsoluteFill>
      </Sequence>

      {/* ─── 7. 半自动执行 ─── */}
      <Sequence from={executeRange[0]} durationInFrames={executeRange[1] - executeRange[0] + 1}>
        <AbsoluteFill
          style={{
            background: COLORS.bg,
            padding: "80px 100px",
            justifyContent: "center",
          }}
        >
          <SectionHeader title="半自动执行流程" index="05" />
          <FlowStep step={1} title="点击开始执行" desc="系统生成 Pack + 交接单 + 执行记录" delay={5} />
          <FlowStep step={2} title="人工切换 ccswitch" desc="手动选择推荐模型" delay={20} />
          <FlowStep step={3} title="在 Codex 中执行" desc="将 Pack 粘贴到 AI 对话中开始开发" delay={35} />
          <FlowStep step={4} title="回写 AIOS" desc="填写实际模型、测试结果、完成总结" delay={50} />
          <FlowStep step={5} title="自动记录" desc="changelog / memory / 执行记录自动更新" delay={65} />
        </AbsoluteFill>
      </Sequence>

      {/* ─── 8. 多项目启动器 ─── */}
      <Sequence from={launcherRange[0]} durationInFrames={launcherRange[1] - launcherRange[0] + 1}>
        <AbsoluteFill
          style={{
            background: COLORS.bg,
            padding: "80px 100px",
            justifyContent: "center",
            alignItems: "center",
          }}
        >
          <SectionHeader title="多项目统一管理" index="06" />
          <MockWindow titleBar="AIOS Launcher —  http://127.0.0.1:8755">
            <div style={{ display: "flex", gap: 16, flexWrap: "wrap" }}>
              <ProjectCard name="xiazhi-ai" path="~/Github/xiazhi-ai.git" status="running" tasks={12} />
              <ProjectCard name="dashboard_o" path="~/Github/dashboard_o" status="stopped" tasks={5} />
              <ProjectCard name="ecosystem-hub" path="~/Github/ecosystem-hub" status="running" tasks={8} />
            </div>
          </MockWindow>
        </AbsoluteFill>
      </Sequence>

      {/* ─── 9. 核心能力概述 ─── */}
      <Sequence from={featuresRange[0]} durationInFrames={featuresRange[1] - featuresRange[0] + 1}>
        <AbsoluteFill
          style={{
            background: COLORS.bg,
            padding: "80px 100px",
            justifyContent: "center",
          }}
        >
          <SectionHeader title="完整能力矩阵" index="能力清单" />
          <FeatureGrid
            features={[
              { icon: "🔍", title: "项目扫描与索引", desc: "自动识别项目结构、技术栈、文件组成" },
              { icon: "📋", title: "任务管理", desc: "创建、拆解、跟踪、回写任务全生命周期" },
              { icon: "🤖", title: "智能路由", desc: "任务特征匹配合适模型，降低选型成本" },
              { icon: "📦", title: "Context Pack", desc: "自动生成包含背景、规则、文件的结构化上下文" },
              { icon: "🚀", title: "半自动执行", desc: "开始-执行-回写闭环，执行记录可追溯" },
              { icon: "🏠", title: "多项目管理", desc: "统一首页管理多个项目，独立 .aios/ 数据" },
              { icon: "💾", title: "自动恢复", desc: "失败分类 + 差异化自动重试 + 冷却护栏" },
              { icon: "📊", title: "成本统计", desc: "模型单价 + Token 估算 + 项目预算策略" },
            ]}
          />
        </AbsoluteFill>
      </Sequence>

      {/* ─── 10. 完整工作流 ─── */}
      <Sequence from={flowRange[0]} durationInFrames={flowRange[1] - flowRange[0] + 1}>
        <AbsoluteFill
          style={{
            background: COLORS.bg,
            padding: "80px 100px",
            justifyContent: "center",
          }}
        >
          <SectionHeader title="推荐工作流" index="完整流程" />
          <FlowStep step={1} title="注册项目" desc="在启动器首页添加项目目录" delay={5} />
          <FlowStep step={2} title="初始化 + 扫描" desc="创建 .aios/ 并扫描项目结构" delay={20} />
          <FlowStep step={3} title="设定目标 + 拆解任务" desc="写入目标描述，AIOS 自动拆分" delay={35} />
          <FlowStep step={4} title="选择任务 + 开始执行" desc="系统推荐模型，生成 Pack 和交接单" delay={50} />
          <FlowStep step={5} title="去 Codex 中开发" desc="人工切模型，粘贴 Pack 开始编码" delay={65} />
          <FlowStep step={6} title="回写完成" desc="确认结果，填测试信息，AIOS 记录一切" delay={80} />
        </AbsoluteFill>
      </Sequence>

      {/* ─── 11. CLI 命令速览 ─── */}
      <Sequence from={cliRange[0]} durationInFrames={cliRange[1] - cliRange[0] + 1}>
        <AbsoluteFill
          style={{
            background: COLORS.bg,
            padding: "80px 100px",
            justifyContent: "center",
          }}
        >
          <SectionHeader title="CLI 命令速览" index="命令" />
          <div style={{ display: "flex", gap: 40 }}>
            <div style={{ flex: 1 }}>
              <CLICommand cmd="aios init" desc="初始化 .aios/ 知识目录" delay={5} />
              <CLICommand cmd="aios scan" desc="扫描项目文件结构" delay={15} />
              <CLICommand cmd="aios task create" desc="创建开发任务" delay={25} />
              <CLICommand cmd="aios task plan" desc="目标拆解为子任务" delay={35} />
              <CLICommand cmd="aios route" desc="查看模型推荐" delay={45} />
              <CLICommand cmd="aios pack" desc="生成 Context Pack" delay={55} />
            </div>
            <div style={{ flex: 1 }}>
              <CLICommand cmd="aios run --manual" desc="手动开始执行" delay={10} />
              <CLICommand cmd="aios ccswitch export" desc="导出 ccswitch 适配文件" delay={20} />
              <CLICommand cmd="aios handoff" desc="生成任务交接单" delay={30} />
              <CLICommand cmd="aios model probe" desc="探测模型可用性" delay={40} />
              <CLICommand cmd="aios web" desc="启动单项目 Web UI" delay={50} />
              <CLICommand cmd="aios launcher" desc="启动多项目首页" delay={60} />
            </div>
          </div>
        </AbsoluteFill>
      </Sequence>

      {/* ─── 12. 价值说明 ─── */}
      <Sequence from={valueRange[0]} durationInFrames={valueRange[1] - valueRange[0] + 1}>
        <AbsoluteFill
          style={{
            background: COLORS.bg,
            padding: "80px 100px",
            justifyContent: "center",
            alignItems: "center",
          }}
        >
          <SectionHeader title="核心价值" index="Why AIOS" />
          <div style={{ display: "flex", gap: 32, marginTop: 40 }}>
            <Card style={{ flex: 1, textAlign: "center" }}>
              <div style={{ fontSize: 48, color: COLORS.green, fontWeight: 700, marginBottom: 8 }}>
                3-5x
              </div>
              <div style={{ color: COLORS.white, fontSize: 18, fontWeight: 600, marginBottom: 8 }}>
                效率提升
              </div>
              <div style={{ color: COLORS.muted, fontSize: 14 }}>
                任务拆解 + 模型推荐 + Pack 自动化
              </div>
            </Card>
            <Card style={{ flex: 1, textAlign: "center" }}>
              <div style={{ fontSize: 48, color: COLORS.accent, fontWeight: 700, marginBottom: 8 }}>
                100%
              </div>
              <div style={{ color: COLORS.white, fontSize: 18, fontWeight: 600, marginBottom: 8 }}>
                上下文不丢失
              </div>
              <div style={{ color: COLORS.muted, fontSize: 14 }}>
                每次切换模型都有结构化 Pack
              </div>
            </Card>
            <Card style={{ flex: 1, textAlign: "center" }}>
              <div style={{ fontSize: 48, color: COLORS.purple, fontWeight: 700, marginBottom: 8 }}>
                可追溯
              </div>
              <div style={{ color: COLORS.white, fontSize: 18, fontWeight: 600, marginBottom: 8 }}>
                执行全链路
              </div>
              <div style={{ color: COLORS.muted, fontSize: 14 }}>
                谁、何时、用什么模型、什么结果
              </div>
            </Card>
          </div>
        </AbsoluteFill>
      </Sequence>

      {/* ─── 13. 结尾 ─── */}
      <Sequence from={outroRange[0]} durationInFrames={outroRange[1] - outroRange[0] + 1}>
        <TitleSlide
          title="开始使用 AIOS"
          subtitle="github.com/YX-NAS/AIOS · v0.38.0 · Apache-2.0"
          accentColor={COLORS.green}
        />
      </Sequence>
    </AbsoluteFill>
  );
};
