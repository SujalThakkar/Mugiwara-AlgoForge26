export interface Lesson {
    id: string;
    title: string;
    duration: number;
    completed: boolean;
    type: 'video' | 'article' | 'quiz' | 'calculator';
    content?: string;
    videoUrl?: string;
    quiz?: {
        questions: Array<{
            question: string;
            options: string[];
            correctAnswer: number;
            explanation: string;
        }>;
    };
}

export interface Course {
    id: string;
    title: string;
    description: string;
    icon: string;
    color: string;
    difficulty: 'beginner' | 'intermediate' | 'advanced';
    duration: number;
    lessons: Lesson[];
    progress: number;
    enrolled: boolean;
}

export const courses: Course[] = [
    {
        id: 'compound-interest',
        title: 'Understanding Compound Interest',
        description: 'Learn how money grows exponentially over time',
        icon: '📈',
        color: '#10B981',
        difficulty: 'beginner',
        duration: 25,
        progress: 100,
        enrolled: true,
        lessons: [
            {
                id: 'ci_1',
                title: 'What is Compound Interest?',
                duration: 8,
                completed: true,
                type: 'video',
                content: 'Compound interest helps your money earn returns on past returns.',
            },
            {
                id: 'ci_2',
                title: 'The Power of Compounding',
                duration: 10,
                completed: true,
                type: 'article',
                content: '# The Power of Compounding\n\nConsistency matters more than timing.',
            },
            {
                id: 'ci_3',
                title: 'Compound Interest Calculator',
                duration: 7,
                completed: true,
                type: 'calculator',
            },
        ],
    },
    {
        id: 'good-vs-bad-debt',
        title: 'Good Debt vs Bad Debt',
        description: 'Learn which liabilities build your future and which ones drain it',
        icon: '💳',
        color: '#3B82F6',
        difficulty: 'beginner',
        duration: 20,
        progress: 60,
        enrolled: true,
        lessons: [
            {
                id: 'debt_1',
                title: 'What Makes Debt Good?',
                duration: 7,
                completed: true,
                type: 'video',
            },
            {
                id: 'debt_2',
                title: 'The Debt Trap',
                duration: 8,
                completed: true,
                type: 'article',
            },
            {
                id: 'debt_3',
                title: 'Quiz: Test Your Knowledge',
                duration: 5,
                completed: false,
                type: 'quiz',
                quiz: {
                    questions: [
                        {
                            question: 'Which option is usually considered good debt?',
                            options: ['Vacation loan', 'Home loan', 'Shopping EMI', 'Payday loan'],
                            correctAnswer: 1,
                            explanation: 'A home loan can fund an appreciating asset.',
                        },
                    ],
                },
            },
        ],
    },
    {
        id: 'tax-planning',
        title: 'Tax Planning Basics',
        description: 'Save tax legally with smart planning',
        icon: '💰',
        color: '#EF4444',
        difficulty: 'intermediate',
        duration: 40,
        progress: 0,
        enrolled: false,
        lessons: [
            {
                id: 'tax_1',
                title: 'Understanding 80C Deductions',
                duration: 12,
                completed: false,
                type: 'video',
            },
            {
                id: 'tax_2',
                title: 'HRA and Home Loan Benefits',
                duration: 15,
                completed: false,
                type: 'article',
            },
            {
                id: 'tax_3',
                title: 'Tax Calculator',
                duration: 8,
                completed: false,
                type: 'calculator',
            },
        ],
    },
    {
        id: 'emergency-fund',
        title: 'Building an Emergency Fund',
        description: 'Prepare for life’s unexpected expenses',
        icon: '🛡️',
        color: '#06B6D4',
        difficulty: 'beginner',
        duration: 20,
        progress: 0,
        enrolled: false,
        lessons: [
            {
                id: 'ef_1',
                title: 'Why You Need Emergency Funds',
                duration: 7,
                completed: false,
                type: 'video',
            },
            {
                id: 'ef_2',
                title: 'How Much Should You Save?',
                duration: 8,
                completed: false,
                type: 'article',
            },
        ],
    },
];

export const getCourseById = (id: string) => courses.find((course) => course.id === id);
