<script setup lang="ts">
const props = defineProps<{
  price: string
  compareAtPrice?: string | null
  size?: 'md' | 'lg'
}>()

const { format } = useMoney()
</script>

<template>
  <!-- flex-wrap: в сумах цены длинные — старая цена переносится, а не вылезает за карточку -->
  <div class="flex flex-wrap items-baseline gap-x-2 gap-y-0.5" :class="props.size === 'lg' ? 'text-2xl' : 'text-base'">
    <span class="font-medium" :class="{ 'text-gold-700': compareAtPrice }">{{ format(price) }}</span>
    <s v-if="compareAtPrice" class="text-sm text-muted">{{ format(compareAtPrice) }}</s>
  </div>
</template>
