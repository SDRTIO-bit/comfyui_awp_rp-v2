import { useEffect, useState } from "react";
import { Modal, Select, Typography, message } from "antd";
import {
  Card,
  createSession,
  GreetingInfo,
  listCards,
  listGreetings,
} from "../api/client";

const { Text } = Typography;

interface NewSessionModalProps {
  open: boolean;
  onClose: () => void;
  onCreated: () => void;
}

function getErrorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

export default function NewSessionModal({ open, onClose, onCreated }: NewSessionModalProps) {
  const [cards, setCards] = useState<Card[]>([]);
  const [cardId, setCardId] = useState("");
  const [greetings, setGreetings] = useState<GreetingInfo[]>([]);
  const [greetingId, setGreetingId] = useState("");
  const [creating, setCreating] = useState(false);
  const [loadingCards, setLoadingCards] = useState(false);
  const [loadingGreetings, setLoadingGreetings] = useState(false);

  useEffect(() => {
    if (!open) return;
    setLoadingCards(true);
    listCards()
      .then(setCards)
      .catch((error) => message.error(getErrorMessage(error)))
      .finally(() => setLoadingCards(false));
  }, [open]);

  useEffect(() => {
    if (!cardId) {
      setGreetings([]);
      setGreetingId("");
      return;
    }
    setGreetingId("");
    setLoadingGreetings(true);
    listGreetings(cardId)
      .then((items) => {
        setGreetings(items);
        const defaultGreeting = items.find((item) => item.is_default) || items[0];
        setGreetingId(defaultGreeting?.greeting_id || "");
      })
      .catch(() => setGreetings([]))
      .finally(() => setLoadingGreetings(false));
  }, [cardId]);

  const closeAndReset = () => {
    setCardId("");
    setGreetings([]);
    setGreetingId("");
    onClose();
  };

  const handleCreate = async () => {
    if (!cardId || !greetingId) {
      message.warning("请先选择角色卡和开场白");
      return;
    }
    setCreating(true);
    try {
      await createSession(cardId, greetingId);
      message.success("会话已创建");
      onCreated();
      closeAndReset();
    } catch (error) {
      message.error(getErrorMessage(error));
    } finally {
      setCreating(false);
    }
  };

  return (
    <Modal
      title="新建会话"
      open={open}
      okText="创建"
      confirmLoading={creating}
      onOk={handleCreate}
      onCancel={closeAndReset}
    >
      <Text type="secondary">角色卡</Text>
      <Select
        showSearch
        loading={loadingCards}
        optionFilterProp="label"
        options={cards.map((card) => ({ value: card.card_id, label: card.name }))}
        placeholder="选择角色卡"
        style={{ width: "100%", marginTop: 8 }}
        value={cardId || undefined}
        onChange={setCardId}
      />

      <Text type="secondary" style={{ display: "block", marginTop: 16 }}>
        开场白
      </Text>
      <Select
        loading={loadingGreetings}
        disabled={!cardId}
        options={greetings.map((greeting) => ({
          value: greeting.greeting_id,
          label: `${greeting.label || greeting.greeting_id}${greeting.is_default ? "（默认）" : ""}`,
        }))}
        placeholder={cardId ? "选择开场白" : "请先选择角色卡"}
        style={{ width: "100%", marginTop: 8 }}
        value={greetingId || undefined}
        onChange={setGreetingId}
      />
    </Modal>
  );
}
