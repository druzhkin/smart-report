"use client";

import { useEffect, useMemo, useState } from "react";
import { motion } from "framer-motion";
import { Check, Eye, EyeOff, KeyRound, Loader2, Mail, ShieldAlert, Wallet } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { usePushNotifications } from "@/hooks/usePushNotifications";
import { cn, formatCost } from "@/lib/utils";

const API_BASE = "/api";

type KeyName =
  | "OPENROUTER_API_KEY"
  | "PERPLEXITY_API_KEY"
  | "DEEPGRAM_API_KEY"
  | "RAGFLOW_API_KEY";

type KeyStatusMap = Record<KeyName, "set" | "not_set">;
type BudgetMap = Record<"light" | "standard" | "deep" | "exhaustive", number>;

const KEY_LABELS: Record<KeyName, string> = {
  OPENROUTER_API_KEY: "OPENROUTER_API_KEY",
  PERPLEXITY_API_KEY: "PERPLEXITY_API_KEY",
  DEEPGRAM_API_KEY: "DEEPGRAM_API_KEY",
  RAGFLOW_API_KEY: "RAGFLOW_API_KEY",
};

const BUDGET_LIMITS: Record<keyof BudgetMap, { min: number; max: number; step: number; label: string }> = {
  light: { min: 0.1, max: 1.0, step: 0.05, label: "Light" },
  standard: { min: 0.5, max: 5.0, step: 0.1, label: "Standard" },
  deep: { min: 1.0, max: 10.0, step: 0.25, label: "Deep" },
  exhaustive: { min: 5.0, max: 30.0, step: 0.5, label: "Exhaustive" },
};

const DEFAULT_BUDGETS: BudgetMap = {
  light: 0.5,
  standard: 2,
  deep: 5,
  exhaustive: 15,
};

const DEFAULT_PUBLIC_PRICING: BudgetMap = {
  light: 0.5,
  standard: 2,
  deep: 5,
  exhaustive: 15,
};

function Toggle({
  checked,
  onChange,
  disabled,
}: {
  checked: boolean;
  onChange: (next: boolean) => void;
  disabled?: boolean;
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      disabled={disabled}
      onClick={() => onChange(!checked)}
      className={cn(
        "relative inline-flex h-6 w-11 items-center rounded-full transition-colors",
        checked ? "bg-primary" : "bg-muted",
        disabled && "cursor-not-allowed opacity-50"
      )}
    >
      <span
        className={cn(
          "inline-block h-5 w-5 rounded-full bg-white shadow transition-transform",
          checked ? "translate-x-5" : "translate-x-1"
        )}
      />
    </button>
  );
}

function ApiKeyRow({
  keyName,
  label,
  value,
  isVisible,
  isSaving,
  status,
  onChange,
  onToggleVisibility,
  onSave,
}: {
  keyName: KeyName;
  label: string;
  value: string;
  isVisible: boolean;
  isSaving: boolean;
  status: "set" | "not_set";
  onChange: (value: string) => void;
  onToggleVisibility: () => void;
  onSave: () => void;
}) {
  return (
    <div className="rounded-xl border border-border/70 bg-background/60 p-4">
      <div className="mb-3 flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <span className="text-sm font-medium">{label}</span>
          {status === "set" ? (
            <span className="inline-flex items-center gap-1 rounded-full bg-emerald-100 px-2.5 py-1 text-xs font-medium text-emerald-700">
              <Check className="h-3.5 w-3.5" />
              set
            </span>
          ) : (
            <span className="rounded-full bg-muted px-2.5 py-1 text-xs text-muted-foreground">
              not set
            </span>
          )}
        </div>
        <code className="text-xs text-muted-foreground">{keyName}</code>
      </div>

      <div className="flex flex-col gap-3 md:flex-row">
        <div className="relative flex-1">
          <Input
            type={isVisible ? "text" : "password"}
            value={value}
            onChange={(event) => onChange(event.target.value)}
            placeholder="Введите API ключ"
            className="pr-11"
          />
          <button
            type="button"
            onClick={onToggleVisibility}
            className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground"
            aria-label={isVisible ? "Скрыть ключ" : "Показать ключ"}
          >
            {isVisible ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
          </button>
        </div>

        <Button type="button" onClick={onSave} disabled={isSaving || !value.trim()} className="md:min-w-28">
          {isSaving ? <Loader2 className="h-4 w-4 animate-spin" /> : "Сохранить"}
        </Button>
      </div>
    </div>
  );
}

export default function SettingsPage() {
  const [keyValues, setKeyValues] = useState<Record<KeyName, string>>({
    OPENROUTER_API_KEY: "",
    PERPLEXITY_API_KEY: "",
    DEEPGRAM_API_KEY: "",
    RAGFLOW_API_KEY: "",
  });
  const [keyStatuses, setKeyStatuses] = useState<KeyStatusMap>({
    OPENROUTER_API_KEY: "not_set",
    PERPLEXITY_API_KEY: "not_set",
    DEEPGRAM_API_KEY: "not_set",
    RAGFLOW_API_KEY: "not_set",
  });
  const [visibleKeys, setVisibleKeys] = useState<Record<KeyName, boolean>>({
    OPENROUTER_API_KEY: false,
    PERPLEXITY_API_KEY: false,
    DEEPGRAM_API_KEY: false,
    RAGFLOW_API_KEY: false,
  });
  const [savingKeys, setSavingKeys] = useState<Partial<Record<KeyName, boolean>>>({});
  const [budgets, setBudgets] = useState<BudgetMap>(DEFAULT_BUDGETS);
  const [publicPricing, setPublicPricing] = useState<BudgetMap>(DEFAULT_PUBLIC_PRICING);
  const [savingBudget, setSavingBudget] = useState(false);
  const [savingPricing, setSavingPricing] = useState(false);
  const [emailEnabled, setEmailEnabled] = useState(false);
  const [email, setEmail] = useState("");
  const [pushEnabled, setPushEnabled] = useState(false);
  const [clearingLibrary, setClearingLibrary] = useState(false);
  const [loading, setLoading] = useState(true);
  const [notice, setNotice] = useState<string | null>(null);
  const { isSupported: pushSupported, requestPermission } = usePushNotifications(null);

  useEffect(() => {
    const storedEmailEnabled = window.localStorage.getItem("settings.emailEnabled");
    const storedEmail = window.localStorage.getItem("settings.email");
    setEmailEnabled(storedEmailEnabled === "true");
    setEmail(storedEmail ?? "");
    setPushEnabled(typeof Notification !== "undefined" && Notification.permission === "granted");
  }, []);

  useEffect(() => {
    window.localStorage.setItem("settings.emailEnabled", String(emailEnabled));
    window.localStorage.setItem("settings.email", email);
  }, [email, emailEnabled]);

  useEffect(() => {
    async function loadSettings() {
      try {
        const [keysResponse, budgetResponse, pricingResponse] = await Promise.all([
          fetch(`${API_BASE}/settings/keys`, { cache: "no-store" }),
          fetch(`${API_BASE}/settings/budget`, { cache: "no-store" }),
          fetch(`${API_BASE}/settings/pricing`, { cache: "no-store" }),
        ]);

        if (keysResponse.ok) {
          const keysData = (await keysResponse.json()) as KeyStatusMap;
          setKeyStatuses(keysData);
        }

        if (budgetResponse.ok) {
          const budgetData = (await budgetResponse.json()) as BudgetMap;
          setBudgets(budgetData);
        }

        if (pricingResponse.ok) {
          const pricingData = (await pricingResponse.json()) as BudgetMap;
          setPublicPricing(pricingData);
        }
      } catch (error) {
        console.error(error);
      } finally {
        setLoading(false);
      }
    }

    loadSettings();
  }, []);

  useEffect(() => {
    if (!notice) return;
    const timeoutId = window.setTimeout(() => setNotice(null), 2500);
    return () => window.clearTimeout(timeoutId);
  }, [notice]);

  const keyEntries = useMemo(
    () => (Object.keys(KEY_LABELS) as KeyName[]).map((keyName) => ({ keyName, label: KEY_LABELS[keyName] })),
    []
  );

  async function saveKey(keyName: KeyName) {
    try {
      setSavingKeys((current) => ({ ...current, [keyName]: true }));
      const response = await fetch(`${API_BASE}/settings/keys`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ key_name: keyName, value: keyValues[keyName] }),
      });
      if (!response.ok) throw new Error(`Failed to save ${keyName}`);

      setKeyStatuses((current) => ({ ...current, [keyName]: "set" }));
      setNotice(`${keyName} сохранён`);
    } catch (error) {
      console.error(error);
      setNotice(`Не удалось сохранить ${keyName}`);
    } finally {
      setSavingKeys((current) => ({ ...current, [keyName]: false }));
    }
  }

  async function saveBudget() {
    try {
      setSavingBudget(true);
      const response = await fetch(`${API_BASE}/settings/budget`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(budgets),
      });
      if (!response.ok) throw new Error("Failed to save budget");
      setNotice("Бюджетные лимиты обновлены");
    } catch (error) {
      console.error(error);
      setNotice("Не удалось сохранить бюджет");
    } finally {
      setSavingBudget(false);
    }
  }

  async function savePricing() {
    try {
      setSavingPricing(true);
      const response = await fetch(`${API_BASE}/settings/pricing`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(publicPricing),
      });
      if (!response.ok) throw new Error("Failed to save pricing");
      setNotice("Публичные цены обновлены");
    } catch (error) {
      console.error(error);
      setNotice("Не удалось сохранить публичные цены");
    } finally {
      setSavingPricing(false);
    }
  }

  async function handlePushToggle(next: boolean) {
    if (!next) {
      setPushEnabled(false);
      return;
    }

    try {
      const permission = await requestPermission();
      setPushEnabled(permission === "granted");
      setNotice(permission === "granted" ? "Push-уведомления включены" : "Разрешение не выдано");
    } catch (error) {
      console.error(error);
      setNotice("Не удалось включить push-уведомления");
    }
  }

  async function clearLibrary() {
    if (!window.confirm("Очистить всю Knowledge Library? Это действие нельзя отменить.")) {
      return;
    }

    try {
      setClearingLibrary(true);
      const response = await fetch(`${API_BASE}/library/all`, { method: "DELETE" });
      if (!response.ok) throw new Error("Failed to clear library");
      setNotice("Knowledge Library очищена");
    } catch (error) {
      console.error(error);
      setNotice("Не удалось очистить Knowledge Library");
    } finally {
      setClearingLibrary(false);
    }
  }

  return (
    <div className="mx-auto max-w-5xl space-y-8">
      <div className="space-y-2">
        <h1 className="text-3xl font-semibold tracking-tight text-foreground">Настройки</h1>
        <p className="max-w-2xl text-sm leading-6 text-muted-foreground">
          Управление API-ключами, бюджетами, уведомлениями и библиотекой знаний Smart Report System.
        </p>
      </div>

      {notice ? (
        <div className="rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-700">
          {notice}
        </div>
      ) : null}

      <div className="grid gap-6">
        <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }}>
          <Card>
            <CardHeader>
              <div className="flex items-center gap-3">
                <div className="rounded-2xl bg-primary/10 p-3 text-primary">
                  <KeyRound className="h-5 w-5" />
                </div>
                <div>
                  <CardTitle>API Keys</CardTitle>
                  <CardDescription>Серверные ключи для LLM, поиска, voice и knowledge library.</CardDescription>
                </div>
              </div>
            </CardHeader>
            <CardContent className="space-y-4">
              {loading ? (
                <div className="space-y-3">
                  <div className="h-24 animate-pulse rounded-xl bg-muted" />
                  <div className="h-24 animate-pulse rounded-xl bg-muted" />
                </div>
              ) : (
                keyEntries.map(({ keyName, label }) => (
                  <ApiKeyRow
                    key={keyName}
                    keyName={keyName}
                    label={label}
                    value={keyValues[keyName]}
                    isVisible={visibleKeys[keyName]}
                    isSaving={Boolean(savingKeys[keyName])}
                    status={keyStatuses[keyName]}
                    onChange={(value) =>
                      setKeyValues((current) => ({
                        ...current,
                        [keyName]: value,
                      }))
                    }
                    onToggleVisibility={() =>
                      setVisibleKeys((current) => ({
                        ...current,
                        [keyName]: !current[keyName],
                      }))
                    }
                    onSave={() => saveKey(keyName)}
                  />
                ))
              )}
            </CardContent>
          </Card>
        </motion.div>

        <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.05 }}>
          <Card>
            <CardHeader>
              <div className="flex items-center gap-3">
                <div className="rounded-2xl bg-sky-100 p-3 text-sky-700">
                  <Wallet className="h-5 w-5" />
                </div>
                <div>
                  <CardTitle>Budget Limits</CardTitle>
                  <CardDescription>Максимальные лимиты затрат для каждого режима глубины исследования.</CardDescription>
                </div>
              </div>
            </CardHeader>
            <CardContent className="space-y-6">
              {(Object.keys(BUDGET_LIMITS) as Array<keyof BudgetMap>).map((budgetKey) => {
                const config = BUDGET_LIMITS[budgetKey];
                const value = budgets[budgetKey];

                return (
                  <div key={budgetKey} className="space-y-3">
                    <div className="flex items-center justify-between gap-4">
                      <div>
                        <p className="font-medium">{config.label}</p>
                        <p className="text-sm text-muted-foreground">
                          Диапазон {formatCost(config.min)} - {formatCost(config.max)}
                        </p>
                      </div>
                      <div className="rounded-full bg-secondary px-3 py-1 text-sm font-medium">
                        {formatCost(value)}
                      </div>
                    </div>
                    <input
                      type="range"
                      min={config.min}
                      max={config.max}
                      step={config.step}
                      value={value}
                      onChange={(event) =>
                        setBudgets((current) => ({
                          ...current,
                          [budgetKey]: Number(event.target.value),
                        }))
                      }
                      className="h-2 w-full cursor-pointer appearance-none rounded-full bg-muted accent-primary"
                    />
                  </div>
                );
              })}

              <div className="flex justify-end">
                <Button type="button" onClick={saveBudget} disabled={savingBudget}>
                  {savingBudget ? <Loader2 className="h-4 w-4 animate-spin" /> : "Сохранить лимиты"}
                </Button>
              </div>
            </CardContent>
          </Card>
        </motion.div>

        <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.1 }}>
          <Card>
            <CardHeader>
              <div className="flex items-center gap-3">
                <div className="rounded-2xl bg-emerald-100 p-3 text-emerald-700">
                  <Wallet className="h-5 w-5" />
                </div>
                <div>
                  <CardTitle>Public Prices</CardTitle>
                  <CardDescription>Цены, которые показываются пользователю на лендинге и перед запуском исследования.</CardDescription>
                </div>
              </div>
            </CardHeader>
            <CardContent className="space-y-6">
              {(Object.keys(BUDGET_LIMITS) as Array<keyof BudgetMap>).map((pricingKey) => {
                const config = BUDGET_LIMITS[pricingKey];
                const value = publicPricing[pricingKey];

                return (
                  <div key={pricingKey} className="space-y-3">
                    <div className="flex items-center justify-between gap-4">
                      <div>
                        <p className="font-medium">{config.label}</p>
                        <p className="text-sm text-muted-foreground">
                          Видимая цена на сайте: {formatCost(value)}
                        </p>
                      </div>
                      <div className="rounded-full bg-secondary px-3 py-1 text-sm font-medium">
                        {formatCost(value)}
                      </div>
                    </div>
                    <input
                      type="range"
                      min={config.min}
                      max={config.max}
                      step={config.step}
                      value={value}
                      onChange={(event) =>
                        setPublicPricing((current) => ({
                          ...current,
                          [pricingKey]: Number(event.target.value),
                        }))
                      }
                      className="h-2 w-full cursor-pointer appearance-none rounded-full bg-muted accent-primary"
                    />
                  </div>
                );
              })}

              <div className="flex justify-end">
                <Button type="button" onClick={savePricing} disabled={savingPricing}>
                  {savingPricing ? <Loader2 className="h-4 w-4 animate-spin" /> : "Сохранить цены"}
                </Button>
              </div>
            </CardContent>
          </Card>
        </motion.div>

        <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.15 }}>
          <Card>
            <CardHeader>
              <div className="flex items-center gap-3">
                <div className="rounded-2xl bg-amber-100 p-3 text-amber-700">
                  <Mail className="h-5 w-5" />
                </div>
                <div>
                  <CardTitle>Notifications</CardTitle>
                  <CardDescription>Управление email и push-уведомлениями о готовности отчёта.</CardDescription>
                </div>
              </div>
            </CardHeader>
            <CardContent className="space-y-5">
              <div className="flex items-start justify-between gap-4 rounded-xl border border-border/70 p-4">
                <div className="space-y-1">
                  <p className="font-medium">Email when report is ready</p>
                  <p className="text-sm text-muted-foreground">Получать письмо, когда QA завершит отчёт со статусом PASS.</p>
                </div>
                <Toggle checked={emailEnabled} onChange={setEmailEnabled} />
              </div>

              <Input
                type="email"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                disabled={!emailEnabled}
                placeholder="you@example.com"
              />

              <div className="flex items-start justify-between gap-4 rounded-xl border border-border/70 p-4">
                <div className="space-y-1">
                  <p className="font-medium">Push notifications</p>
                  <p className="text-sm text-muted-foreground">
                    Использует browser push и service worker для уведомления о готовности отчёта.
                  </p>
                </div>
                <Toggle checked={pushEnabled} onChange={handlePushToggle} disabled={!pushSupported} />
              </div>

              {!pushSupported ? (
                <p className="text-sm text-muted-foreground">Этот браузер не поддерживает push-уведомления.</p>
              ) : null}
            </CardContent>
          </Card>
        </motion.div>

        <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.2 }}>
          <Card className="border-rose-200">
            <CardHeader>
              <div className="flex items-center gap-3">
                <div className="rounded-2xl bg-rose-100 p-3 text-rose-700">
                  <ShieldAlert className="h-5 w-5" />
                </div>
                <div>
                  <CardTitle>Danger Zone</CardTitle>
                  <CardDescription>Необратимые действия для knowledge library и связанных данных.</CardDescription>
                </div>
              </div>
            </CardHeader>
            <CardContent className="flex flex-col gap-4 rounded-b-xl bg-rose-50/50">
              <div>
                <p className="font-medium text-rose-900">Clear Knowledge Library</p>
                <p className="mt-1 text-sm text-rose-700">
                  Удаляет документы из подключённых RAGFlow datasets. Перед очисткой появится подтверждение.
                </p>
              </div>
              <div>
                <Button type="button" variant="destructive" onClick={clearLibrary} disabled={clearingLibrary}>
                  {clearingLibrary ? <Loader2 className="h-4 w-4 animate-spin" /> : "Clear Knowledge Library"}
                </Button>
              </div>
            </CardContent>
          </Card>
        </motion.div>
      </div>
    </div>
  );
}
