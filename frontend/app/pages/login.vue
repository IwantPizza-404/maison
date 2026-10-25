<script setup lang="ts">
import { useAuthStore } from '~/stores/auth'
import { useWishlistStore } from '~/stores/wishlist'
import type { AuthCustomer, AuthMethods } from '~/types/catalog'

const { t } = useI18n()
const api = useApi()
const route = useRoute()
const localePath = useLocalePath()
const auth = useAuthStore()
const wishlist = useWishlistStore()

const { data: methods } = await useAsyncData('auth-methods', () => api<AuthMethods>('/auth/methods'), {
  default: () => ({ telegram: false, sms: false, whatsapp: false }),
})

// SMS и WhatsApp — вход по номеру телефона: одинаковая форма, разный канал доставки кода
type Method = 'telegram' | 'sms' | 'whatsapp'
const method = ref<Method>('telegram')
const step = ref<'start' | 'code'>('start')
const token = ref<string | null>(null)
const botUrl = ref<string | null>(null)
const phone = ref('')
const code = ref<string[]>([])
const error = ref<string | null>(null)
const loading = ref(false)

function errorText(e: unknown): string {
  const response = (e as { response?: { status?: number; _data?: { detail?: unknown } } }).response
  if (response?.status === 429) return t('checkout.errors.tooMany')
  const detail = response?._data?.detail
  return typeof detail === 'string' ? detail : t('login.error')
}

// Ссылку на бота готовим заранее: кнопка — обычная ссылка, браузер не блокирует новую вкладку
async function prepareTelegram() {
  error.value = null
  try {
    const data = await api<{ token: string; bot_url: string }>('/auth/telegram/start', { method: 'POST' })
    token.value = data.token
    botUrl.value = data.bot_url
  } catch (e) {
    error.value = errorText(e)
  }
}

async function sendCode() {
  loading.value = true
  error.value = null
  try {
    const data = await api<{ token: string }>(`/auth/${method.value}/start`, { method: 'POST', body: { phone: phone.value } })
    token.value = data.token
    step.value = 'code'
  } catch (e) {
    error.value = errorText(e)
  } finally {
    loading.value = false
  }
}

async function verify() {
  const value = code.value.join('')
  if (!token.value || value.length !== 6) return
  loading.value = true
  error.value = null
  try {
    const customer = await api<AuthCustomer>('/auth/verify', { method: 'POST', body: { token: token.value, code: value } })
    auth.set(customer)
    await wishlist.syncAfterLogin()
    const redirect = typeof route.query.redirect === 'string' && route.query.redirect.startsWith('/') ? route.query.redirect : null
    await navigateTo(redirect ?? localePath('/account'))
  } catch (e) {
    error.value = errorText(e)
    code.value = []
  } finally {
    loading.value = false
  }
}

function switchMethod(value: Method) {
  method.value = value
  step.value = 'start'
  code.value = []
  error.value = null
  token.value = null
  if (value === 'telegram') prepareTelegram()
}

onMounted(() => {
  if (auth.isLoggedIn) return navigateTo(localePath('/account'))
  if (!methods.value.telegram) method.value = methods.value.whatsapp ? 'whatsapp' : 'sms'
  if (method.value === 'telegram' && methods.value.telegram) prepareTelegram()
})

const tabs = computed(() => [
  ...(methods.value.telegram ? [{ label: 'Telegram', value: 'telegram', icon: 'i-simple-icons-telegram' }] : []),
  ...(methods.value.whatsapp ? [{ label: 'WhatsApp', value: 'whatsapp', icon: 'i-simple-icons-whatsapp' }] : []),
  ...(methods.value.sms ? [{ label: 'SMS', value: 'sms', icon: 'i-lucide-message-square' }] : []),
])

const codeHint = computed(() => t(`login.${method.value}.codeHint`))

useSeoMeta({ title: () => t('login.title'), robots: 'noindex' })
</script>

<template>
  <UContainer class="max-w-md py-16">
    <h1 class="font-serif text-4xl">{{ t('login.title') }}</h1>
    <p class="mt-3 text-muted">{{ t('login.subtitle') }}</p>

    <UAlert
      v-if="!tabs.length"
      :title="t('login.unavailable')"
      color="neutral"
      variant="soft"
      icon="i-lucide-info"
      class="mt-8"
    />

    <template v-else>
      <UTabs
        v-if="tabs.length > 1"
        :items="tabs"
        :model-value="method"
        :content="false"
        color="neutral"
        class="mt-8"
        @update:model-value="switchMethod($event as Method)"
      />

      <div class="mt-8 space-y-6">
        <!-- Шаг 1: Telegram — открыть бота -->
        <template v-if="method === 'telegram' && step === 'start'">
          <ol class="space-y-2 text-sm text-muted">
            <li>1. {{ t('login.telegram.step1') }}</li>
            <li>2. {{ t('login.telegram.step2') }}</li>
            <li>3. {{ t('login.telegram.step3') }}</li>
          </ol>
          <UButton
            :to="botUrl ?? undefined"
            target="_blank"
            :loading="!botUrl && !error"
            :disabled="!botUrl"
            :label="t('login.telegram.open')"
            icon="i-simple-icons-telegram"
            color="neutral"
            size="xl"
            block
            class="bg-ink text-gold-500 hover:bg-stone-800"
            @click="step = 'code'"
          />
        </template>

        <!-- Шаг 1: SMS или WhatsApp — номер телефона -->
        <form v-if="method !== 'telegram' && step === 'start'" class="space-y-4" @submit.prevent="sendCode">
          <UFormField :label="t('checkout.phone')">
            <UInput v-model="phone" type="tel" autocomplete="tel" placeholder="+998 90 123 45 67" size="xl" class="w-full" />
          </UFormField>
          <UButton type="submit" :label="t('login.sms.send')" :loading="loading" color="neutral" size="xl" block class="bg-ink text-gold-500 hover:bg-stone-800" />
        </form>

        <!-- Шаг 2: код -->
        <form v-if="step === 'code'" class="space-y-5" @submit.prevent="verify">
          <p class="text-sm text-muted">{{ codeHint }}</p>
          <UPinInput
            v-model="code"
            :length="6"
            otp
            size="xl"
            autofocus
            class="justify-center"
            @complete="verify"
          />
          <UButton type="submit" :label="t('login.submit')" :loading="loading" color="neutral" size="xl" block class="bg-ink text-gold-500 hover:bg-stone-800" />
          <div class="flex justify-between text-sm">
            <UButton v-if="method === 'telegram' && botUrl" :to="botUrl" target="_blank" :label="t('login.telegram.reopen')" variant="link" color="neutral" />
            <UButton :label="t('login.back')" variant="link" color="neutral" @click="switchMethod(method)" />
          </div>
        </form>

        <UAlert v-if="error" :title="error" color="error" variant="soft" icon="i-lucide-circle-alert" />
      </div>
    </template>
  </UContainer>
</template>
