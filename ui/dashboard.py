"""
CktMem 性能监控面板

使用 Streamlit 可视化 CktMem 的性能指标：
- 会话选择
- 核心指标（总轮次、总 Token、总花费、压缩次数）
- Token 消耗图
- 记忆层级透视
"""

import streamlit as st
import sqlite3
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime
from pathlib import Path
import sys

# 添加项目根目录到 Python 路径
PROJECT_ROOT = Path(__file__).parent.parent.resolve()
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from cktmem.token_counter import TokenCounter


# 配置页面
st.set_page_config(
    page_title="CktMem 性能监控",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)


class DashboardData:
    """Dashboard 数据访问层"""

    def __init__(self, db_path: str = "cktclaw_sessions.db"):
        self.db_path = db_path
        self.token_counter = TokenCounter()

    def get_connection(self):
        """获取数据库连接"""
        return sqlite3.connect(self.db_path)

    def get_all_sessions(self):
        """获取所有会话"""
        conn = self.get_connection()
        query = """
            SELECT
                session_id,
                project_name,
                model_choice,
                created_at,
                updated_at,
                total_compactions
            FROM sessions
            ORDER BY updated_at DESC
        """
        df = pd.read_sql_query(query, conn)
        conn.close()
        return df

    def get_session_info(self, session_id: str):
        """获取会话基本信息"""
        conn = self.get_connection()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("""
            SELECT * FROM sessions WHERE session_id = ?
        """, (session_id,))

        row = cursor.fetchone()
        conn.close()

        if row:
            return dict(row)
        return None

    def get_session_messages(self, session_id: str):
        """获取会话所有消息"""
        conn = self.get_connection()
        query = """
            SELECT
                id,
                role,
                content,
                msg_type,
                layer,
                created_at,
                metadata
            FROM messages
            WHERE session_id = ?
            ORDER BY created_at ASC
        """
        df = pd.read_sql_query(query, conn, params=(session_id,))
        conn.close()

        # 转换时间戳
        df['created_at'] = pd.to_datetime(df['created_at'])

        return df

    def get_compact_history(self, session_id: str):
        """获取压缩历史"""
        conn = self.get_connection()
        query = """
            SELECT
                compact_type,
                pre_compact_tokens,
                post_compact_tokens,
                tokens_saved,
                created_at
            FROM compact_history
            WHERE session_id = ?
            ORDER BY created_at ASC
        """
        df = pd.read_sql_query(query, conn, params=(session_id,))
        conn.close()

        if not df.empty:
            df['created_at'] = pd.to_datetime(df['created_at'])

        return df

    def calculate_tokens(self, messages_df):
        """计算消息的 Token 数"""
        tokens = []
        for _, row in messages_df.iterrows():
            content = row['content'] or ""
            token_count = self.token_counter._estimate_text(content)
            tokens.append(token_count)

        messages_df['tokens'] = tokens
        return messages_df

    def get_layer_distribution(self, messages_df):
        """获取四层上下文的 Token 分布"""
        layer_tokens = messages_df.groupby('layer')['tokens'].sum().to_dict()

        # 确保所有层都存在
        layers = ['system', 'project', 'session', 'turn']
        result = {layer: layer_tokens.get(layer, 0) for layer in layers}

        return result


def render_sidebar(data: DashboardData):
    """渲染侧边栏"""
    st.sidebar.title("📊 CktMem 监控面板")
    st.sidebar.markdown("---")

    # 获取所有会话
    sessions_df = data.get_all_sessions()

    if sessions_df.empty:
        st.sidebar.warning("⚠️ 暂无会话数据")
        return None

    # 会话选择
    st.sidebar.subheader("选择会话")

    # 格式化会话选项
    session_options = []
    for _, row in sessions_df.iterrows():
        label = f"{row['session_id'][:8]}... ({row['project_name'] or 'Unnamed'})"
        session_options.append((label, row['session_id']))

    selected_label = st.sidebar.selectbox(
        "Session ID",
        options=[opt[0] for opt in session_options],
        index=0,
    )

    # 获取选中的 session_id
    selected_session_id = None
    for label, sid in session_options:
        if label == selected_label:
            selected_session_id = sid
            break

    # 显示会话信息
    if selected_session_id:
        session_info = data.get_session_info(selected_session_id)
        st.sidebar.markdown("---")
        st.sidebar.markdown("**会话信息**")
        st.sidebar.text(f"项目: {session_info.get('project_name', 'N/A')}")
        st.sidebar.text(f"模型: {session_info.get('model_choice', 'N/A')}")
        st.sidebar.text(f"创建时间: {session_info.get('created_at', 'N/A')[:19]}")

    st.sidebar.markdown("---")
    st.sidebar.markdown("**关于**")
    st.sidebar.info(
        "CktMem 是 CktClaw 的四层上下文记忆系统，"
        "支持自动压缩和语义隔离。"
    )

    return selected_session_id


def render_metrics(data: DashboardData, session_id: str, messages_df, compact_df):
    """渲染核心指标"""
    st.header("📈 核心指标")

    # 计算指标
    total_messages = len(messages_df)
    total_turns = len(messages_df[messages_df['role'].isin(['user', 'assistant'])])
    total_tokens = messages_df['tokens'].sum() if 'tokens' in messages_df.columns else 0
    total_compactions = len(compact_df)

    # 计算总花费（假设 DeepSeek 价格：$0.14/1M input tokens, $0.28/1M output tokens）
    # 简化计算：假设 input:output = 3:1
    input_tokens = total_tokens * 0.75
    output_tokens = total_tokens * 0.25
    total_cost = (input_tokens * 0.14 / 1_000_000) + (output_tokens * 0.28 / 1_000_000)

    # 显示指标卡片
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric(
            label="总轮次",
            value=f"{total_turns}",
            delta=f"{total_messages} 条消息",
        )

    with col2:
        st.metric(
            label="总 Token 数",
            value=f"{total_tokens:,}",
            delta=f"{total_tokens / max(total_turns, 1):.0f} tokens/轮",
        )

    with col3:
        st.metric(
            label="总花费 (估算)",
            value=f"${total_cost:.4f}",
            delta=f"${total_cost / max(total_turns, 1):.6f}/轮",
        )

    with col4:
        st.metric(
            label="压缩触发次数",
            value=f"{total_compactions}",
            delta=f"{compact_df['tokens_saved'].sum():,} tokens 节省" if not compact_df.empty else "未压缩",
        )


def render_token_chart(messages_df, compact_df):
    """渲染 Token 消耗图"""
    st.header("📊 Token 消耗趋势")

    if messages_df.empty:
        st.warning("暂无消息数据")
        return

    # 计算累积 Token
    messages_df['cumulative_tokens'] = messages_df['tokens'].cumsum()
    messages_df['turn_number'] = range(1, len(messages_df) + 1)

    # 创建图表
    fig = go.Figure()

    # Token 增长曲线
    fig.add_trace(go.Scatter(
        x=messages_df['turn_number'],
        y=messages_df['cumulative_tokens'],
        mode='lines+markers',
        name='累积 Token',
        line=dict(color='#1f77b4', width=2),
        marker=dict(size=4),
        hovertemplate='<b>轮次 %{x}</b><br>累积 Token: %{y:,}<extra></extra>',
    ))

    # 标记压缩点
    if not compact_df.empty:
        for _, compact in compact_df.iterrows():
            compact_time = compact['created_at']
            # 找到最接近的消息
            closest_idx = (messages_df['created_at'] - compact_time).abs().idxmin()
            closest_turn = messages_df.loc[closest_idx, 'turn_number']
            closest_tokens = messages_df.loc[closest_idx, 'cumulative_tokens']

            fig.add_trace(go.Scatter(
                x=[closest_turn],
                y=[closest_tokens],
                mode='markers',
                name=f'压缩 ({compact["compact_type"]})',
                marker=dict(
                    size=12,
                    color='red',
                    symbol='x',
                    line=dict(width=2, color='darkred'),
                ),
                hovertemplate=f'<b>压缩点</b><br>类型: {compact["compact_type"]}<br>'
                              f'节省: {compact["tokens_saved"]:,} tokens<extra></extra>',
            ))

    # 添加阈值线
    fig.add_hline(
        y=150_000,
        line_dash="dash",
        line_color="orange",
        annotation_text="自动压缩阈值 (150K)",
        annotation_position="right",
    )

    fig.update_layout(
        xaxis_title="轮次",
        yaxis_title="累积 Token 数",
        hovermode='x unified',
        height=400,
        showlegend=True,
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1
        ),
    )

    st.plotly_chart(fig, use_container_width=True)


def render_layer_distribution(layer_tokens):
    """渲染记忆层级透视"""
    st.header("🧠 记忆层级透视")

    col1, col2 = st.columns([1, 1])

    with col1:
        # 饼图
        labels = ['System', 'Project', 'Session', 'Turn']
        values = [
            layer_tokens['system'],
            layer_tokens['project'],
            layer_tokens['session'],
            layer_tokens['turn'],
        ]
        colors = ['#ff7f0e', '#2ca02c', '#d62728', '#1f77b4']

        fig_pie = go.Figure(data=[go.Pie(
            labels=labels,
            values=values,
            hole=0.4,
            marker=dict(colors=colors),
            textinfo='label+percent',
            hovertemplate='<b>%{label}</b><br>Token: %{value:,}<br>占比: %{percent}<extra></extra>',
        )])

        fig_pie.update_layout(
            title="四层上下文 Token 分布",
            height=400,
        )

        st.plotly_chart(fig_pie, use_container_width=True)

    with col2:
        # 柱状图
        df_layers = pd.DataFrame({
            'Layer': labels,
            'Tokens': values,
        })

        fig_bar = px.bar(
            df_layers,
            x='Layer',
            y='Tokens',
            color='Layer',
            color_discrete_sequence=colors,
            text='Tokens',
        )

        fig_bar.update_traces(
            texttemplate='%{text:,}',
            textposition='outside',
        )

        fig_bar.update_layout(
            title="各层 Token 数量",
            xaxis_title="上下文层级",
            yaxis_title="Token 数",
            showlegend=False,
            height=400,
        )

        st.plotly_chart(fig_bar, use_container_width=True)

    # 层级说明
    st.markdown("---")
    st.markdown("**四层上下文说明：**")

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.markdown("**🔧 System Layer**")
        st.caption("系统 Prompt、工具定义、全局规则")

    with col2:
        st.markdown("**📁 Project Layer**")
        st.caption("项目级静态信息、长期知识库")

    with col3:
        st.markdown("**💾 Session Layer**")
        st.caption("Anchor Memory、Core Context、压缩摘要")

    with col4:
        st.markdown("**💬 Turn Layer**")
        st.caption("最近 N 轮对话、当前用户输入")


def render_compact_history(compact_df):
    """渲染压缩历史"""
    st.header("🗜️ 压缩历史")

    if compact_df.empty:
        st.info("暂无压缩记录")
        return

    # 格式化数据
    display_df = compact_df.copy()
    display_df['created_at'] = display_df['created_at'].dt.strftime('%Y-%m-%d %H:%M:%S')
    display_df['压缩率'] = (display_df['tokens_saved'] / display_df['pre_compact_tokens'] * 100).round(2)

    # 重命名列
    display_df = display_df.rename(columns={
        'compact_type': '压缩类型',
        'pre_compact_tokens': '压缩前 Token',
        'post_compact_tokens': '压缩后 Token',
        'tokens_saved': '节省 Token',
        'created_at': '压缩时间',
    })

    # 显示表格
    st.dataframe(
        display_df[['压缩时间', '压缩类型', '压缩前 Token', '压缩后 Token', '节省 Token', '压缩率']],
        use_container_width=True,
        hide_index=True,
    )

    # 统计信息
    col1, col2, col3 = st.columns(3)

    with col1:
        st.metric("总压缩次数", len(compact_df))

    with col2:
        st.metric("总节省 Token", f"{compact_df['tokens_saved'].sum():,}")

    with col3:
        avg_compression = (compact_df['tokens_saved'] / compact_df['pre_compact_tokens'] * 100).mean()
        st.metric("平均压缩率", f"{avg_compression:.2f}%")


def main():
    """主函数"""
    # 标题
    st.title("📊 CktMem 性能监控面板")
    st.markdown("实时监控 CktClaw 的四层上下文记忆系统性能")
    st.markdown("---")

    # 初始化数据访问层
    db_path = Path(PROJECT_ROOT) / "cktclaw_sessions.db"

    if not db_path.exists():
        st.error(f"❌ 数据库文件不存在: {db_path}")
        st.info("请先运行 CktClaw 创建会话数据")
        return

    data = DashboardData(str(db_path))

    # 渲染侧边栏并获取选中的会话
    selected_session_id = render_sidebar(data)

    if not selected_session_id:
        st.warning("请在侧边栏选择一个会话")
        return

    # 加载会话数据
    with st.spinner("加载会话数据..."):
        messages_df = data.get_session_messages(selected_session_id)
        compact_df = data.get_compact_history(selected_session_id)

        # 计算 Token
        if not messages_df.empty:
            messages_df = data.calculate_tokens(messages_df)

    # 渲染各个部分
    if not messages_df.empty:
        render_metrics(data, selected_session_id, messages_df, compact_df)
        st.markdown("---")
        render_token_chart(messages_df, compact_df)
        st.markdown("---")

        # 计算层级分布
        layer_tokens = data.get_layer_distribution(messages_df)
        render_layer_distribution(layer_tokens)

        st.markdown("---")
        render_compact_history(compact_df)
    else:
        st.warning("该会话暂无消息数据")

    # 页脚
    st.markdown("---")
    st.markdown(
        "<div style='text-align: center; color: gray;'>"
        "CktClaw - The Autonomous Multi-Agent EDA Ecosystem | "
        "Powered by Harness Engineering & CktMem"
        "</div>",
        unsafe_allow_html=True,
    )


if __name__ == "__main__":
    main()
