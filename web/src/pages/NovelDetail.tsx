import { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import {
  Button, Card, Col, Descriptions, Empty, List, Row, Space, Spin, Tag, Typography, message,
  Collapse, Drawer,
} from "antd";
import {
  ArrowLeftOutlined, BookOutlined, EditOutlined, TeamOutlined, BulbOutlined,
} from "@ant-design/icons";
import {
  getNovelProject, listNovelCharacters, listNovelChapterPlans, writeNovelChapter,
  NovelProject, NovelCharacter, NovelChapterPlan, NovelDraft,
} from "../api/client";

const { Text, Paragraph, Title } = Typography;

function getErrorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

export default function NovelDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [project, setProject] = useState<NovelProject | null>(null);
  const [characters, setCharacters] = useState<NovelCharacter[]>([]);
  const [chapters, setChapters] = useState<NovelChapterPlan[]>([]);
  const [loading, setLoading] = useState(true);
  const [writing, setWriting] = useState<number | null>(null);
  const [draftDrawer, setDraftDrawer] = useState<{ open: boolean; draft: NovelDraft | null }>({ open: false, draft: null });

  const load = () => {
    if (!id) return;
    setLoading(true);
    Promise.all([
      getNovelProject(id).catch(() => null),
      listNovelCharacters(id).catch(() => []),
      listNovelChapterPlans(id).catch(() => []),
    ]).then(([proj, chars, chaps]) => {
      setProject(proj);
      setCharacters(chars);
      setChapters(chaps);
    }).finally(() => setLoading(false));
  };

  useEffect(() => { load(); }, [id]);

  const handleWrite = async (chapterIndex: number) => {
    if (!id) return;
    setWriting(chapterIndex);
    try {
      const draft = await writeNovelChapter(id, chapterIndex);
      setDraftDrawer({ open: true, draft });
      message.success(`第${chapterIndex}章写作完成：${draft.char_count} 字`);
    } catch (error) {
      message.error(getErrorMessage(error));
    } finally {
      setWriting(null);
    }
  };

  if (loading) return <Spin size="large" style={{ display: "block", margin: "100px auto" }} />;
  if (!project) return <Empty description="项目不存在" />;

  return (
    <div>
      <div style={{ display: "flex", alignItems: "center", marginBottom: 16, gap: 12 }}>
        <Button icon={<ArrowLeftOutlined />} onClick={() => navigate("/novels")} />
        <Title level={4} style={{ margin: 0 }}>{project.title}</Title>
        <Tag>{project.genre}</Tag>
        <Tag>{project.status}</Tag>
      </div>

      <Row gutter={[16, 16]}>
        <Col span={16}>
          <Card title="项目信息" size="small">
            <Descriptions column={1} size="small">
              <Descriptions.Item label="一句话简介">{project.one_sentence_pitch}</Descriptions.Item>
              <Descriptions.Item label="目标平台">{project.target_platform}</Descriptions.Item>
              <Descriptions.Item label="目标读者">{project.target_reader}</Descriptions.Item>
              <Descriptions.Item label="核心情绪">{project.core_emotion}</Descriptions.Item>
            </Descriptions>
          </Card>

          <Card title={<><BookOutlined /> 章节计划</>} size="small" style={{ marginTop: 16 }}>
            {chapters.length ? (
              <List
                dataSource={chapters}
                renderItem={(ch) => (
                  <List.Item
                    extra={
                      <Button
                        type="primary"
                        size="small"
                        icon={<EditOutlined />}
                        loading={writing === ch.chapter_index}
                        onClick={() => handleWrite(ch.chapter_index)}
                      >
                        写作
                      </Button>
                    }
                  >
                    <List.Item.Meta
                      title={`第${ch.chapter_index}章：${ch.title}`}
                      description={
                        <Space direction="vertical" size={0}>
                          <Text type="secondary">目标 {ch.target_chars} 字 | {ch.target_emotion}</Text>
                          <Text type="secondary">钩子：{ch.ending_design?.hook_type} ({ch.ending_design?.hook_strength})</Text>
                        </Space>
                      }
                    />
                  </List.Item>
                )}
              />
            ) : (
              <Empty description="暂无章节计划" />
            )}
          </Card>
        </Col>

        <Col span={8}>
          <Card title={<><TeamOutlined /> 角色</>} size="small">
            {characters.length ? (
              <List
                dataSource={characters}
                renderItem={(char) => (
                  <List.Item>
                    <List.Item.Meta
                      title={char.name}
                      description={
                        <>
                          <Tag>{char.role}</Tag>
                          <Paragraph ellipsis={{ rows: 2 }} style={{ margin: "4px 0 0", color: "#666", fontSize: 12 }}>
                            {char.personality}
                          </Paragraph>
                        </>
                      }
                    />
                  </List.Item>
                )}
              />
            ) : (
              <Empty description="暂无角色" />
            )}
          </Card>

          <Card title={<><BulbOutlined /> 世界观</>} size="small" style={{ marginTop: 16 }}>
            <Paragraph type="secondary" style={{ fontSize: 12 }}>
              世界观详情请查看项目创建时生成的大纲。
            </Paragraph>
          </Card>
        </Col>
      </Row>

      <Drawer
        title="章节正文"
        open={draftDrawer.open}
        onClose={() => setDraftDrawer({ open: false, draft: null })}
        width={700}
      >
        {draftDrawer.draft && (
          <>
            <Descriptions size="small" column={3}>
              <Descriptions.Item label="字数">{draftDrawer.draft.char_count}</Descriptions.Item>
              <Descriptions.Item label="状态"><Tag>{draftDrawer.draft.status}</Tag></Descriptions.Item>
              <Descriptions.Item label="版本">r{draftDrawer.draft.revision}</Descriptions.Item>
            </Descriptions>
            <div style={{ marginTop: 16, whiteSpace: "pre-wrap", lineHeight: 1.8, fontSize: 14 }}>
              {draftDrawer.draft.text}
            </div>
          </>
        )}
      </Drawer>
    </div>
  );
}
