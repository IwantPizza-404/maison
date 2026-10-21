<script setup lang="ts">
import type { AccordionItem } from '@nuxt/ui'
import type { ListFilterKey } from '~/composables/useCatalogQuery'
import type { CatalogFilters, SpecOption } from '~/types/catalog'

// hideTitle — в выезжающей панели заголовок «Фильтры» уже есть в её шапке
const props = defineProps<{ filters: CatalogFilters; hideBrand?: boolean; hideTitle?: boolean }>()

const { t } = useI18n()
const catalog = useCatalogQuery()

type Option = { value: string; label: string }
type FilterItem = AccordionItem & { key: ListFilterKey; options: Option[] }

const fromSpec = (items: SpecOption[]): Option[] => items.map((o) => ({ value: o.slug, label: o.name }))

const groups = computed<FilterItem[]>(() => {
  const all: [ListFilterKey, string, Option[]][] = [
    ['brand', t('filters.brand'), props.filters.brands.map((b) => ({ value: b.slug, label: b.name }))],
    ['condition', t('filters.condition'), props.filters.conditions],
    ['availability', t('filters.availability'), props.filters.availability],
    ['gender', t('filters.gender'), props.filters.genders],
    ['movement', t('filters.movement'), props.filters.movements],
    ['case_material', t('filters.caseMaterial'), fromSpec(props.filters.case_materials)],
    ['dial_color', t('filters.dialColor'), fromSpec(props.filters.dial_colors)],
    ['strap_material', t('filters.strapMaterial'), fromSpec(props.filters.strap_materials)],
  ]
  return all
    .filter(([key, , options]) => options.length && !(props.hideBrand && key === 'brand'))
    .map(([key, label, options]) => ({ key, label, options, value: key }))
})

// Раскрыты первые группы и все, где уже что-то выбрано
const opened = computed(() =>
  groups.value
    .filter((g, index) => index < 3 || catalog.lists.value[g.key].length)
    .map((g) => g.key),
)

function select(key: ListFilterKey, values: string[]) {
  const current = catalog.lists.value[key]
  const changed = values.find((v) => !current.includes(v)) ?? current.find((v) => !values.includes(v))
  if (changed) catalog.toggle(key, changed)
}

const priceMin = ref<number | undefined>()
const priceMax = ref<number | undefined>()
watch(
  [catalog.priceMin, catalog.priceMax],
  ([min, max]) => {
    priceMin.value = min ? Number(min) : undefined
    priceMax.value = max ? Number(max) : undefined
  },
  { immediate: true },
)

function applyPrice() {
  catalog.setPrice(priceMin.value?.toString(), priceMax.value?.toString())
}
</script>

<template>
  <div>
    <div class="flex items-center justify-between pb-2">
      <h2 :class="props.hideTitle ? 'sr-only' : 'text-sm font-medium uppercase tracking-wider'">{{ t('filters.title') }}</h2>
      <UButton
        v-if="catalog.activeCount.value"
        :label="t('filters.reset')"
        variant="link"
        color="neutral"
        size="xs"
        class="ml-auto"
        @click="catalog.reset()"
      />
    </div>

    <UAccordion type="multiple" :items="groups" :default-value="opened" :ui="{ trigger: 'text-sm uppercase tracking-wider' }">
      <template #body="{ item }">
        <UCheckboxGroup
          :items="item.options"
          :model-value="catalog.lists.value[item.key]"
          color="neutral"
          @update:model-value="select(item.key, $event as string[])"
        />
      </template>
    </UAccordion>

    <form class="py-4" @submit.prevent="applyPrice">
      <p class="mb-3 text-sm font-medium uppercase tracking-wider">{{ t('filters.price') }}, USD</p>
      <div class="flex items-center gap-2">
        <UInputNumber
          v-model="priceMin"
          :min="0"
          :placeholder="t('filters.from')"
          :increment="false"
          :decrement="false"
          @blur="applyPrice"
        />
        <span class="text-muted">—</span>
        <UInputNumber
          v-model="priceMax"
          :min="0"
          :placeholder="t('filters.to')"
          :increment="false"
          :decrement="false"
          @blur="applyPrice"
        />
      </div>
    </form>
  </div>
</template>
