import JobDetail from '../../components/job-detail';

export default function JobDetailPage({ params }: { params: { id: string } }) {
  return <JobDetail jobId={params.id} />;
}
