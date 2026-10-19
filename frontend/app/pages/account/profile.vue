<script setup lang="ts">
import { useAuthStore } from '~/stores/auth'
import { CURRENCIES, type Currency, useCurrencyStore } from '~/stores/currency'
import type { Address, AddressPayload, AuthCustomer, CheckoutOptions } from '~/types/catalog'

const { t, locale, locales, setLocale } = useI18n()
const api = useApi()
const toast = useToast()
const auth = useAuthStore()
const currency = useCurrencyStore()

type Language = 'en' | 'ru' | 'uz'
const profile = reactive({
  name: auth.customer?.name ?? '',
  email: auth.customer?.email ?? '',
  language: (auth.customer?.language ?? locale.value) as Language,
  currency: (auth.customer?.currency ?? 'USD') as Currency,
  notify_telegram: auth.customer?.notify_telegram ?? true,
})
const saving = ref(false)

async function saveProfile() {
  saving.value = true
  try {
    const updated = await api<AuthCustomer>('/account/me', {
      method: 'PATCH',
      body: { ...profile, email: profile.email || null },
    })
    auth.set(updated)
    currency.set(updated.currency as Currency)
    toast.add({ title: t('account.profile.saved'), icon: 'i-lucide-check' })
    // Язык профиля — и язык сайта; setLocale запоминает выбор в cookie, иначе на английский не переключить
    if (updated.language !== locale.value) await setLocale(updated.language as Language)
  } catch {
    toast.add({ title: t('login.error'), color: 'error' })
  } finally {
    saving.value = false
  }
}

const { data: addresses, refresh } = await useAsyncData('account-addresses', () => api<Address[]>('/account/addresses'), {
  default: () => [],
})
const { data: options } = await useAsyncData('checkout-options', () => api<CheckoutOptions>('/checkout/options'), { watch: [locale] })
const countryItems = computed(() => (options.value?.countries ?? []).map((c) => ({ value: c.code, label: c.name })))
const countryName = (code: string) => options.value?.countries.find((c) => c.code === code)?.name ?? code

// Добавление и правка адреса — в модальном окне
const editorOpen = ref(false)
const editing = ref<number | null>(null)
const form = reactive<AddressPayload>({ country: 'UZ', city: '', address: '', is_default: false })

function openEditor(address?: Address) {
  editing.value = address?.id ?? null
  Object.assign(form, address ?? { country: 'UZ', city: '', address: '', is_default: !addresses.value.length })
  editorOpen.value = true
}

async function saveAddress() {
  const path = editing.value ? `/account/addresses/${editing.value}` : '/account/addresses'
  await api(path, { method: editing.value ? 'PUT' : 'POST', body: form })
  editorOpen.value = false
  await refresh()
}

async function removeAddress(id: number) {
  await api(`/account/addresses/${id}`, { method: 'DELETE' })
  await refresh()
}

const languageItems = computed(() => locales.value.map((l) => ({ value: l.code as Language, label: l.name ?? l.code })))
useSeoMeta({ title: () => t('account.nav.profile') })
</script>

<template>
  <div class="space-y-12">
    <section>
      <h2 class="font-serif text-2xl">{{ t('account.nav.profile') }}</h2>
      <form class="mt-6 grid gap-4 sm:grid-cols-2" @submit.prevent="saveProfile">
        <UFormField :label="t('checkout.name')">
          <UInput v-model="profile.name" autocomplete="name" class="w-full" />
        </UFormField>
        <UFormField :label="t('checkout.phone')" :hint="t('account.profile.phoneHint')">
          <UInput :model-value="auth.customer?.phone" disabled class="w-full" />
        </UFormField>
        <UFormField :label="t('checkout.email')" :hint="t('checkout.optional')">
          <UInput v-model="profile.email" type="email" autocomplete="email" class="w-full" />
        </UFormField>
        <UFormField :label="t('language')">
          <USelect v-model="profile.language" :items="languageItems" class="w-full" />
        </UFormField>
        <UFormField :label="t('currency')">
          <USelect v-model="profile.currency" :items="[...CURRENCIES]" class="w-full" />
        </UFormField>
        <UFormField v-if="auth.customer?.has_telegram" class="sm:col-span-2">
          <USwitch v-model="profile.notify_telegram" :label="t('account.profile.notify')" :description="t('account.profile.notifyHint')" color="neutral" />
        </UFormField>
        <div class="sm:col-span-2">
          <UButton type="submit" :label="t('account.profile.save')" :loading="saving" color="neutral" class="bg-ink text-gold-500 hover:bg-stone-800" />
        </div>
      </form>
    </section>

    <section>
      <div class="flex items-end justify-between">
        <h2 class="font-serif text-2xl">{{ t('account.profile.addresses') }}</h2>
        <UButton :label="t('account.profile.addAddress')" icon="i-lucide-plus" variant="link" color="neutral" @click="openEditor()" />
      </div>
      <ul v-if="addresses.length" class="mt-4 divide-y divide-default">
        <li v-for="address in addresses" :key="address.id" class="flex flex-wrap items-center justify-between gap-3 py-4">
          <div>
            <p>{{ countryName(address.country) }}, {{ address.city }}</p>
            <p v-if="address.address" class="text-sm text-muted">{{ address.address }}</p>
          </div>
          <div class="flex items-center gap-1">
            <UBadge v-if="address.is_default" :label="t('account.profile.default')" color="neutral" variant="soft" size="sm" />
            <UButton icon="i-lucide-pencil" :aria-label="t('account.profile.edit')" variant="ghost" color="neutral" @click="openEditor(address)" />
            <UButton icon="i-lucide-trash-2" :aria-label="t('cart.remove')" variant="ghost" color="neutral" @click="removeAddress(address.id)" />
          </div>
        </li>
      </ul>
      <p v-else class="mt-4 text-muted">{{ t('account.profile.noAddresses') }}</p>
    </section>

    <UModal v-model:open="editorOpen" :title="editing ? t('account.profile.edit') : t('account.profile.addAddress')">
      <template #body>
        <form class="space-y-4" @submit.prevent="saveAddress">
          <UFormField :label="t('checkout.country')" required>
            <USelectMenu v-model="form.country" :items="countryItems" value-key="value" class="w-full" />
          </UFormField>
          <UFormField :label="t('checkout.city')" required>
            <UInput v-model="form.city" required minlength="2" class="w-full" />
          </UFormField>
          <UFormField :label="t('checkout.address')">
            <UInput v-model="form.address" class="w-full" />
          </UFormField>
          <UCheckbox v-model="form.is_default" :label="t('account.profile.makeDefault')" color="neutral" />
          <UButton type="submit" :label="t('account.profile.save')" color="neutral" block class="bg-ink text-gold-500 hover:bg-stone-800" />
        </form>
      </template>
    </UModal>
  </div>
</template>
