"use client";

import { Slider } from "@/components/ui/slider";
import { Progress } from "@/components/ui/progress";
import { formatCurrency } from "@/lib/utils";
import { useTranslation } from "@/lib/hooks/useTranslation";
import { TranslationKey } from "@/lib/translations";

const categoryMapping: Record<string, TranslationKey> = {
    'Shopping': 'cat_shopping',
    'Food & Drink': 'cat_food',
    'Transport': 'cat_transport',
    'Bills': 'cat_bills',
    'Housing': 'cat_housing',
    'Healthcare': 'cat_healthcare',
    'Others': 'cat_others',
};

interface Allocation {
    category: string;
    allocated: number;
    spent: number;
    percentage: number;
}

interface CategoryAllocationProps {
    allocations: Allocation[];
}

export function CategoryAllocation({ allocations }: CategoryAllocationProps) {
    const { t } = useTranslation();

    return (
        <div className="space-y-6">
            {allocations.map((item) => {
                const spentPercentage = (item.spent / item.allocated) * 100;
                const isOverBudget = spentPercentage > 100;

                return (
                    <div key={item.category} className="space-y-2">
                        <div className="flex items-center justify-between">
                            <span className="font-medium text-gray-900">
                                {categoryMapping[item.category] ? t(categoryMapping[item.category]) : item.category}
                            </span>
                            <div className="text-right">
                                <span className={`font-semibold ${isOverBudget ? 'text-coral-600' : 'text-gray-900'}`}>
                                    {formatCurrency(item.spent)}
                                </span>
                                <span className="text-gray-500 text-sm"> / {formatCurrency(item.allocated)}</span>
                            </div>
                        </div>
                        <Progress value={item.spent} max={item.allocated} />
                        <div className="flex items-center justify-between text-xs text-gray-500">
                            <span>{spentPercentage.toFixed(1)}% {t('budget_used_label')}</span>
                            <span>{formatCurrency(item.allocated - item.spent)} {t('remaining_label')}</span>
                        </div>
                    </div>
                );
            })}
        </div>
    );
}
