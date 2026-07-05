import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  Button, Empty, List, Popconfirm, Space, Spin, Tag, Typography, message,
  Modal, Form, Input, Select,
} from "antd";
import { BookOutlined, DeleteOutlined, PlusOutlined, RocketOutlined } from "@ant-design/icons";
import {
  listNovelProjects, deleteNovelProject, planNovelFromConcept, NovelProject, NovelPlanResult,
} from "../api/client";

const { Text, Paragraph } = Typography;
const { TextArea } = Input;

function getErrorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

export default function Novels() {
  const navigate = useNavigate();
  const [projects, setProjects] = useState<NovelProject[]>([]);
  const [loading, setLoading] = useState(true);
  const [planModalOpen, setPlanModalOpen] = useState(false);
  const [planning, setPlanning] = useState(false);
  const [planResult, setPlanResult] = useState<NovelPlanResult | null>(null);
  const [form] = Form.useForm();

  const loadProjects = () => {
    setLoading(true);
    listNovelProjects()
      .then(setProjects)
      .catch((error) => message.error(getErrorMessage(error)))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    loadProjects();
  }, []);

  const handleDelete = async (projectId: string) => {
    try {
      await deleteNovelProject(projectId);
      message.success("项目已删除");
      loadProjects();
    } catch (error) {
      message.error(getErrorMessage(error));
    }
  };

  const handlePlan = async () => {
    try {
      const values = await form.validateFields();
      setPlanning(true);
      const result = await planNovelFromConcept(values);
      setPlanResult(result);
      message.success("大纲生成完成！");
    } catch (error) {
      if (error !== null) message.error(getErrorMessage(error));
    } finally {
      setPlanning(false);
    }
  };

  const handlePlanConfirm = () => {
    setPlanModalOpen(false);
    setPlanResult(null);
    form.resetFields();
    loadProjects();
  };

  return (
    <div>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 16 }}>
        <Text strong style={{ fontSize: 18 }}>小说项目</Text>
        <Space>
          <Button icon={<RocketOutlined />} onClick={() => setPlanModalOpen(true)}>
            AI 生成大纲
          </Button>
          <Button type="primary" icon={<PlusOutlined />} onClick={() => setPlanModalOpen(true)}>
            新建项目
          </Button>
        </Space>
      </div>

      {loading ? (
        <Spin size="large" style={{ display: "block", margin: "100px auto" }} />
      ) : projects.length ? (
        <List
          dataSource={projects}
          renderItem={(project) => (
            <List.Item
              onClick={() => navigate(`/novels/${project.project_id}`)}
              style={{ cursor: "pointer", padding: "12px 16px" }}
              extra={
                <Space onClick={(e) => e.stopPropagation()}>
                  <Tag>{project.genre || "未分类"}</Tag>
                  <Tag>{project.status}</Tag>
                  <Popconfirm
                    title="删除这个项目？"
                    okText="删除"
                    okButtonProps={{ danger: true }}
                    onConfirm={() => handleDelete(project.project_id)}
                  >
                    <Button size="small" danger icon={<DeleteOutlined />} />
                  </Popconfirm>
                </Space>
              }
            >
              <List.Item.Meta
                avatar={<BookOutlined style={{ fontSize: 24, color: "#1677ff" }} />}
                title={project.title}
                description={
                  <Paragraph ellipsis={{ rows: 2 }} style={{ margin: 0, color: "#666" }}>
                    {project.one_sentence_pitch || "暂无简介"}
                  </Paragraph>
                }
              />
            </List.Item>
          )}
        />
      ) : (
        <Empty description="还没有小说项目">
          <Button type="primary" icon={<RocketOutlined />} onClick={() => setPlanModalOpen(true)}>
            AI 生成大纲
          </Button>
        </Empty>
      )}

      <Modal
        title={planResult ? "大纲预览" : "AI 生成小说大纲"}
        open={planModalOpen}
        onCancel={() => { setPlanModalOpen(false); setPlanResult(null); form.resetFields(); }}
        width={planResult ? 800 : 520}
        footer={planResult ? [
          <Button key="ok" type="primary" onClick={handlePlanConfirm}>
            确认，项目已创建
          </Button>,
        ] : [
          <Button key="cancel" onClick={() => { setPlanModalOpen(false); form.resetFields(); }}>
            取消
          </Button>,
          <Button key="plan" type="primary" loading={planning} onClick={handlePlan}>
            生成大纲
          </Button>,
        ]}
      >
        {planResult ? (
          <div style={{ maxHeight: "60vh", overflow: "auto" }}>
            <Paragraph><Text strong>书名：</Text>{planResult.title}</Paragraph>
            <Paragraph><Text strong>题材：</Text>{planResult.genre}</Paragraph>
            <Paragraph><Text strong>一句话：</Text>{planResult.one_sentence_pitch}</Paragraph>
            <Paragraph><Text strong>表层大纲：</Text>{planResult.core_outline?.surface}</Paragraph>
            <Paragraph><Text strong>里层卖点：</Text>{planResult.core_outline?.inner}</Paragraph>
            <Paragraph>
              <Text strong>角色：</Text>
              {planResult.characters?.map((c) => (
                <Tag key={c.name}>{c.name}({c.role})</Tag>
              ))}
            </Paragraph>
            <Paragraph>
              <Text strong>卷计划：</Text>
              {planResult.volumes?.map((v) => (
                <Tag key={v.volume_index}>第{v.volume_index}卷《{v.title}》</Tag>
              ))}
            </Paragraph>
            <Paragraph>
              <Text strong>第一卷：</Text>{planResult.first_volume_chapters?.length} 章
            </Paragraph>
            <Paragraph>
              <Text strong>标签：</Text>
              {planResult.tags?.map((t) => <Tag key={t}>{t}</Tag>)}
            </Paragraph>
          </div>
        ) : (
          <Form form={form} layout="vertical">
            <Form.Item name="concept" label="你的思路（一句话即可）" rules={[{ required: true, message: "请输入你的小说思路" }]}>
              <TextArea rows={3} placeholder="例如：失眠三年的女插画师搬进一栋老房子，发现这栋房子藏着1994年一场事故的秘密" />
            </Form.Item>
            <Form.Item name="title" label="书名（可选，AI 会自动生成）">
              <Input placeholder="留空则自动生成" />
            </Form.Item>
            <Form.Item name="genre" label="题材（可选）">
              <Select allowClear placeholder="选择或留空" options={[
                { value: "都市悬疑", label: "都市悬疑" },
                { value: "玄幻", label: "玄幻" },
                { value: "言情", label: "言情" },
                { value: "科幻", label: "科幻" },
                { value: "恐怖", label: "恐怖" },
                { value: "历史", label: "历史" },
              ]} />
            </Form.Item>
            <Form.Item name="target_platform" label="目标平台（可选）">
              <Select allowClear placeholder="选择或留空" options={[
                { value: "番茄长篇", label: "番茄长篇" },
                { value: "起点", label: "起点" },
                { value: "其他", label: "其他" },
              ]} />
            </Form.Item>
            <Form.Item name="additional_requirements" label="额外要求（可选）">
              <TextArea rows={2} placeholder="例如：要有一个升级体系，主角是女性，不要后宫" />
            </Form.Item>
          </Form>
        )}
      </Modal>
    </div>
  );
}
